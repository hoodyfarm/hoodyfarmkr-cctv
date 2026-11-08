import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

from src.config import settings
from src.services.stream_service import VideoStreamHandler
from src.services.gemini_service import GeminiVisionService
from src.services.oci_service import OCIDataPipelineService
from src.db.session import AsyncSessionLocal, init_db
from src.db.models import CCTVDevice, FrameLog, AIAnalysisResult, AlertEvent
from src.schemas.ai_schema import CCTVAnalysisResultSchema

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    CCTV Stream Processing Pipeline Orchestrator.
    Executes end-to-end flow:
    [RTSP Frame Capture -> Motion Check -> Gemini 2.5 AI Analysis -> PostgreSQL Log -> OCI Upload -> Webhook Alert]
    """
    def __init__(self):
        self.stream_handler = VideoStreamHandler()
        self.gemini_service = GeminiVisionService()
        self.oci_service = OCIDataPipelineService(
            config_file=settings.OCI_CONFIG_FILE,
            profile=settings.OCI_PROFILE,
            raw_bucket=settings.OCI_BUCKET_RAW_VIDEOS,
            refined_bucket=settings.OCI_BUCKET_REFINED_FRAMES
        )
        self._prev_frame = None
        self._running = False
        self._total_processed = 0

    async def run_pipeline_cycle(self) -> Dict[str, Any]:
        """
        Execute 1 complete cycle of the ingestion & AI pipeline.
        """
        self._total_processed += 1
        cycle_id = f"cycle_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{self._total_processed}"
        logger.info(f"🔄 Starting Pipeline Cycle [{cycle_id}]...")

        # 1. RTSP Frame Capture
        frame, is_synthetic = self.stream_handler.capture_frame_with_retry(max_retries=2, delay_sec=0.5)
        if frame is None:
            logger.error("❌ Pipeline Cycle Aborted: Could not capture frame.")
            return {"status": "error", "message": "Frame capture failed"}

        # 2. Motion Delta Calculation
        motion_score = 0.0
        if self._prev_frame is not None:
            motion_score = self.stream_handler.calculate_motion_delta(self._prev_frame, frame)
        self._prev_frame = frame

        # Convert frame to JPEG bytes
        jpeg_bytes = self.stream_handler.frame_to_jpeg_bytes(frame)
        if not jpeg_bytes:
            return {"status": "error", "message": "JPEG encoding failed"}

        # Local File Storage (3500X ??? PC ?? ???/?? ??)
        local_saved_path = None
        try:
            import os
            local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "captures", "frames")
            os.makedirs(local_dir, exist_ok=True)
            local_saved_path = os.path.join(local_dir, f"frame_{cycle_id}.jpg")
            with open(local_saved_path, "wb") as f:
                f.write(jpeg_bytes)
            logger.info(f"Local frame saved: {local_saved_path}")
        except Exception as e:
            logger.warning(f"Failed to save local frame: {e}")

        # 3. Gemini 2.5 Flash Multimodal Vision Analysis
        ai_result: CCTVAnalysisResultSchema = self.gemini_service.analyze_frame_structured(jpeg_bytes)

        # 4. OCI Object Storage Upload (Asynchronous / Fallback)
        oci_url = None
        try:
            filename = f"frames/frame_{cycle_id}.jpg"
            upload_res = self.oci_service.upload_refined_frame(filename, jpeg_bytes)
            if upload_res.get("status") == "success":
                oci_url = upload_res.get("oci_url")
        except Exception as e:
            logger.warning(f"OCI Upload warning: {e}")

        # 5. PostgreSQL DB Record Storage
        db_log_id = None
        try:
            async with AsyncSessionLocal() as session:
                # Store FrameLog
                frame_log = FrameLog(
                    motion_score=motion_score,
                    frame_path_oci=oci_url or f"simulated://{filename}",
                    is_keyframe=True,
                    captured_at=datetime.utcnow()
                )
                session.add(frame_log)
                await session.commit()
                await session.refresh(frame_log)
                db_log_id = frame_log.id

                # Store AIAnalysisResult
                analysis_record = AIAnalysisResult(
                    frame_log_id=frame_log.id,
                    is_anomaly=ai_result.is_anomaly,
                    event_type=ai_result.event_type,
                    confidence_score=ai_result.confidence_score,
                    detected_objects=[obj.model_dump() for obj in ai_result.detected_objects],
                    summary=ai_result.summary,
                    analyzed_at=datetime.utcnow()
                )
                session.add(analysis_record)
                await session.commit()
                await session.refresh(analysis_record)

                # Store AlertEvent if anomaly detected
                if ai_result.is_anomaly or ai_result.recommended_action == "trigger_alarm":
                    alert = AlertEvent(
                        analysis_result_id=analysis_record.id,
                        alert_level="CRITICAL" if ai_result.is_anomaly else "WARNING",
                        webhook_sent=False,
                        created_at=datetime.utcnow()
                    )
                    session.add(alert)
                    await session.commit()
        except Exception as e:
            logger.warning(f"DB Logging warning: {e}")

        # 6. External Webhook Notification (FMS Integration)
        webhook_status = "skipped"
        if (ai_result.is_anomaly or ai_result.recommended_action == "trigger_alarm") and settings.FMS_WEBHOOK_URL:
            webhook_status = await self._send_webhook_notification(ai_result, cycle_id)

        logger.info(f"✅ Pipeline Cycle [{cycle_id}] completed successfully!")
        return {
            "status": "success",
            "cycle_id": cycle_id,
            "is_synthetic": is_synthetic,
            "motion_score": motion_score,
            "ai_result": ai_result.model_dump(),
            "oci_url": oci_url,
            "local_frame_path": local_saved_path,
            "db_frame_log_id": db_log_id,
            "webhook_status": webhook_status
        }

    async def _send_webhook_notification(self, ai_result: CCTVAnalysisResultSchema, cycle_id: str) -> str:
        """
        Send HTTP POST alert payload to external FMS (hoodyfarmkr-fms) webhook.
        """
        payload = {
            "event_source": "hoodyfarmkr-cctv",
            "cycle_id": cycle_id,
            "is_anomaly": ai_result.is_anomaly,
            "event_type": ai_result.event_type,
            "confidence_score": ai_result.confidence_score,
            "summary": ai_result.summary,
            "recommended_action": ai_result.recommended_action,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(settings.FMS_WEBHOOK_URL, json=payload)
                if resp.status_code in (200, 201, 202):
                    return f"success ({resp.status_code})"
                return f"failed ({resp.status_code})"
        except Exception as e:
            logger.warning(f"Webhook notification failed: {e}")
            return f"error ({e})"

pipeline_orchestrator = PipelineOrchestrator()
