import os
import logging
from typing import Any, Dict, Optional

from src.config import settings
from src.core.ports import (
    ClipEncoderPort,
    EventNotifierPort,
    FrameSourcePort,
    ObjectStoragePort,
    VisionAnalyzerPort,
    WorkspaceSinkPort,
)
from src.domain.models.farm_profile import CameraProfile, FarmProfile
from src.services.ingestion_worker import IngestionWorker
from src.services.inference_worker import InferenceWorker
from src.pipeline.event_worker import EventWorker
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.infrastructure.webhook.outbox import WebhookOutbox
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService
from src.services.gemini_service import GeminiVisionService

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    다중 카메라(Multi-Camera) 지원 파이프라인 오케스트레이터.
    - FarmProfile 내 활성 카메라 N대 각각에 대해 (IngestionWorker, InferenceWorker) 페어를 생성
    - 모든 카메라의 이벤트를 단일 공유 EventWorker + WebhookOutbox(로컬 영속 큐 + DLQ)로 수렴
    - 하위 호환성: self.ingestion_worker / self.inference_worker 프로퍼티는 대표(primary) 카메라 워커를 반환
    """

    def __init__(
        self,
        profile: Optional[FarmProfile] = None,
        ingestion_worker: Optional[FrameSourcePort] = None,
        inference_worker: Optional[InferenceWorker] = None,
        event_worker: Optional[EventWorker] = None,
        video_encoder: Optional[ClipEncoderPort] = None,
        fms_client: Optional[EventNotifierPort] = None,
        oci_service: Optional[ObjectStoragePort] = None,
        google_service: Optional[WorkspaceSinkPort] = None,
        vision_service: Optional[VisionAnalyzerPort] = None,
        outbox: Optional[WebhookOutbox] = None,
    ):
        self.profile = profile or FarmProfile.from_settings(settings)
        cam = self.profile.primary_camera
        rules = self.profile.rules
        notif = self.profile.notification
        storage = self.profile.storage

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        clips_dir = os.path.join(base_dir, "captures", "clips")

        self.video_encoder = video_encoder or VideoEncoder(output_dir=clips_dir)
        self.fms_client = fms_client or FMSWebhookClient(
            webhook_url=notif.fms_webhook_url,
            timeout=notif.timeout_sec,
            farm_id=self.profile.farm_id,
            tailscale_host_url=notif.tailscale_host_url,
            media_priority=storage.media_priority,
        )
        self.oci_service = oci_service or OCIDataPipelineService()
        self.google_service = google_service or GoogleIntegrationService()
        self.vision_service = vision_service or GeminiVisionService()
        self.outbox = outbox or WebhookOutbox()

        self.ingestion_workers: Dict[str, FrameSourcePort] = {}
        self.inference_workers: Dict[str, InferenceWorker] = {}

        # Primary camera ingestion worker (DI override or constructed from primary camera profile)
        primary_ingestion = ingestion_worker or IngestionWorker(
            stream_url=cam.rtsp_url,
            target_fps=cam.target_fps,
            max_queue_size=1,
            ring_buffer_sec=cam.ring_buffer_sec,
        )
        self.ingestion_workers[cam.camera_id] = primary_ingestion

        self.event_worker = event_worker or EventWorker(
            ingestion_worker=primary_ingestion,
            video_encoder=self.video_encoder,
            fms_client=self.fms_client,
            oci_service=self.oci_service,
            google_service=self.google_service,
            farm_id=self.profile.farm_id,
            tailscale_host_url=notif.tailscale_host_url,
            media_priority=storage.media_priority,
            outbox=self.outbox,
            frame_sources=self.ingestion_workers,
        )
        self.event_worker.register_frame_source(cam.camera_id, primary_ingestion)

        enable_gemini = bool(settings.GEMINI_API_KEY and "your_" not in settings.GEMINI_API_KEY)
        vision_prompt = rules.build_vision_prompt()

        primary_inference = inference_worker or self._build_inference_worker(
            cam=cam,
            ing_worker=primary_ingestion,
            enable_gemini=enable_gemini,
            vision_prompt=vision_prompt,
        )
        self.inference_workers[cam.camera_id] = primary_inference

        # Build additional enabled cameras defined in FarmProfile (if not overridden by single-camera DI)
        if ingestion_worker is None and inference_worker is None:
            for extra_cam in self.profile.cameras:
                if not extra_cam.enabled or extra_cam.camera_id in self.ingestion_workers:
                    continue
                extra_ing = IngestionWorker(
                    stream_url=extra_cam.rtsp_url,
                    target_fps=extra_cam.target_fps,
                    max_queue_size=1,
                    ring_buffer_sec=extra_cam.ring_buffer_sec,
                )
                self.ingestion_workers[extra_cam.camera_id] = extra_ing
                self.event_worker.register_frame_source(extra_cam.camera_id, extra_ing)
                self.inference_workers[extra_cam.camera_id] = self._build_inference_worker(
                    cam=extra_cam,
                    ing_worker=extra_ing,
                    enable_gemini=enable_gemini,
                    vision_prompt=vision_prompt,
                )

        # Keep backward-compatible attributes pointing to the primary camera workers
        self.ingestion_worker: FrameSourcePort = primary_ingestion
        self.inference_worker: InferenceWorker = primary_inference

    def _build_inference_worker(
        self,
        cam: CameraProfile,
        ing_worker: FrameSourcePort,
        enable_gemini: bool,
        vision_prompt: str,
    ) -> InferenceWorker:
        rules = self.profile.rules
        return InferenceWorker(
            ingestion_worker=ing_worker,
            yolo_model_path=settings.YOLO_MODEL_PATH,
            poll_interval=1.0,
            enable_gemini=enable_gemini,
            event_worker=self.event_worker,
            vision_service=self.vision_service,
            camera_id=cam.camera_id,
            target_classes=rules.target_classes,
            confidence_threshold=rules.confidence_threshold,
            vision_prompt=vision_prompt,
            cooldown_sec=rules.cooldown_sec,
            pre_event_sec=rules.pre_event_sec,
            post_event_sec=rules.post_event_sec,
        )

    @classmethod
    def build_from_profile(cls, profile_path: str, **overrides: Any) -> "WorkerManager":
        """농장 YAML 프로파일 경로로부터 WorkerManager를 조립하는 팩토리"""
        profile = FarmProfile.from_yaml(profile_path)
        return cls(profile=profile, **overrides)

    def start_all(self):
        """모든 카메라 수집/추론 워커 및 공유 이벤트 워커 가동"""
        cam_ids = list(self.ingestion_workers.keys())
        logger.info(
            f"WorkerManager: Starting workers for farm [{self.profile.farm_id}] "
            f"(cameras={cam_ids})..."
        )
        for ing in self.ingestion_workers.values():
            ing.start()
        self.event_worker.start()
        for inf in self.inference_workers.values():
            inf.start()
        logger.info("WorkerManager: All pipeline workers started successfully.")

    def stop_all(self):
        """모든 워커 안전 종료"""
        logger.info("WorkerManager: Stopping workers...")
        for inf in self.inference_workers.values():
            inf.stop()
        self.event_worker.stop()
        for ing in self.ingestion_workers.values():
            ing.stop()
        logger.info("WorkerManager: All workers stopped.")

    def trigger_once(self, camera_id: Optional[str] = None):
        """수동 트리거: 지정된 camera_id(생략 시 대표 카메라)의 최신 프레임 1장을 처리"""
        target_id = camera_id if (camera_id and camera_id in self.ingestion_workers) else self.profile.primary_camera.camera_id
        ing = self.ingestion_workers.get(target_id, self.ingestion_worker)
        inf = self.inference_workers.get(target_id, self.inference_worker)
        frames = ing.get_recent_frames(1)
        if not frames:
            return None
        return inf.process_frame(frames[-1])

    def get_health_summary(self) -> Dict[str, Any]:
        """헬스체크(/health)용 컴포넌트별 상태 요약"""
        outbox_stats = self.outbox.get_stats() if self.outbox else {"pending": 0, "delivered": 0, "dlq": 0}
        cameras_health = {
            cid: {
                "ingestion_running": bool(getattr(ing, "_running", False)),
                "is_connected": bool(getattr(ing, "is_connected", False)),
                "inference_running": bool(getattr(self.inference_workers.get(cid), "_running", False)),
            }
            for cid, ing in self.ingestion_workers.items()
        }
        return {
            "farm_id": self.profile.farm_id,
            "camera_count": len(self.ingestion_workers),
            "event_worker_running": bool(self.event_worker._running),
            "outbox": outbox_stats,
            "cameras": cameras_health,
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """모바일/대시보드/Prometheus용 실시간 관제 메트릭 집계 (다중 카메라 합산 + 개별 상세)"""
        cameras_detail: Dict[str, Any] = {}
        total_captured = 0
        total_reconnects = 0
        total_inferences = 0
        total_filtered = 0
        total_events_saved = 0
        total_anomalies = 0

        for cid, ing in self.ingestion_workers.items():
            inf = self.inference_workers.get(cid, self.inference_worker)
            c_cap = int(getattr(ing, "total_captured", 0))
            c_rec = int(getattr(ing, "reconnect_count", 0))
            c_inf = int(getattr(inf, "total_inferences", 0))
            c_flt = int(getattr(inf, "filtered_count", 0))
            c_evt = int(getattr(inf, "event_saved_count", 0))
            c_ano = int(getattr(inf, "anomaly_count", 0))

            total_captured += c_cap
            total_reconnects += c_rec
            total_inferences += c_inf
            total_filtered += c_flt
            total_events_saved += c_evt
            total_anomalies += c_ano

            cameras_detail[cid] = {
                "ingestion_worker": {
                    "status": "running" if getattr(ing, "_running", False) else "stopped",
                    "is_connected": getattr(ing, "is_connected", False),
                    "target_fps": getattr(ing, "target_fps", 0.0),
                    "total_captured": c_cap,
                    "reconnect_count": c_rec,
                },
                "inference_worker": {
                    "status": "running" if inf._running else "stopped",
                    "total_inferences": c_inf,
                    "filtered_count": c_flt,
                    "event_saved_count": c_evt,
                    "anomaly_count": c_ano,
                    "last_result": inf.last_result,
                },
            }

        outbox_stats = self.outbox.get_stats() if self.outbox else {"pending": 0, "delivered": 0, "dlq": 0}

        return {
            "farm_id": self.profile.farm_id,
            "camera_id": self.profile.primary_camera.camera_id,
            "camera_count": len(self.ingestion_workers),
            "species": self.profile.rules.species,
            "cameras": cameras_detail,
            "ingestion_worker": {
                "status": "running" if getattr(self.ingestion_worker, "_running", False) else "stopped",
                "is_connected": getattr(self.ingestion_worker, "is_connected", False),
                "target_fps": getattr(self.ingestion_worker, "target_fps", 0.0),
                "total_captured": total_captured,
                "reconnect_count": total_reconnects,
            },
            "inference_worker": {
                "status": "running" if self.inference_worker._running else "stopped",
                "total_inferences": total_inferences,
                "filtered_count": total_filtered,
                "event_saved_count": total_events_saved,
                "anomaly_count": total_anomalies,
                "last_result": self.inference_worker.last_result,
            },
            "event_worker": {
                "status": "running" if self.event_worker._running else "stopped",
                "total_events_received": self.event_worker.total_events_received,
                "total_clips_created": self.event_worker.total_clips_created,
                "total_uploads_completed": getattr(self.event_worker, "total_uploads_completed", 0),
                "total_webhooks_sent": self.event_worker.total_webhooks_sent,
                "total_webhooks_queued": getattr(self.event_worker, "total_webhooks_queued", 0),
                "total_sheets_recorded": getattr(self.event_worker, "total_sheets_recorded", 0),
                "total_drive_uploads": getattr(self.event_worker, "total_drive_uploads", 0),
                "queue_size": self.event_worker.event_queue.qsize(),
                "outbox": outbox_stats,
            },
        }


worker_manager = WorkerManager()
