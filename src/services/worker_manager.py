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
from src.domain.models.farm_profile import FarmProfile
from src.services.ingestion_worker import IngestionWorker
from src.services.inference_worker import InferenceWorker
from src.pipeline.event_worker import EventWorker
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService
from src.services.gemini_service import GeminiVisionService

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    3-Worker (IngestionWorker + InferenceWorker + EventWorker) 파이프라인 오케스트레이터.
    - DI(의존성 주입) 생성자 지원: FarmProfile 및 각 Port 구현체를 외부에서 주입 가능
    - build_from_profile() 팩토리 메서드로 농장별 YAML 프로파일 기반 조립 지원
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

        self.ingestion_worker = ingestion_worker or IngestionWorker(
            stream_url=cam.rtsp_url,
            target_fps=cam.target_fps,
            max_queue_size=1,
            ring_buffer_sec=cam.ring_buffer_sec,
        )

        self.event_worker = event_worker or EventWorker(
            ingestion_worker=self.ingestion_worker,
            video_encoder=self.video_encoder,
            fms_client=self.fms_client,
            oci_service=self.oci_service,
            google_service=self.google_service,
            farm_id=self.profile.farm_id,
            tailscale_host_url=notif.tailscale_host_url,
            media_priority=storage.media_priority,
        )

        self.inference_worker = inference_worker or InferenceWorker(
            ingestion_worker=self.ingestion_worker,
            yolo_model_path=settings.YOLO_MODEL_PATH,
            poll_interval=1.0,
            enable_gemini=bool(settings.GEMINI_API_KEY and "your_" not in settings.GEMINI_API_KEY),
            event_worker=self.event_worker,
            vision_service=self.vision_service,
            camera_id=cam.camera_id,
            target_classes=rules.target_classes,
            confidence_threshold=rules.confidence_threshold,
            vision_prompt=rules.build_vision_prompt(),
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
        """3대 워커 백그라운드 스레드 가동"""
        logger.info(
            f"WorkerManager: Starting workers for farm [{self.profile.farm_id}] "
            f"(camera={self.profile.primary_camera.camera_id})..."
        )
        self.ingestion_worker.start()
        self.event_worker.start()
        self.inference_worker.start()
        logger.info("WorkerManager: All 3 pipeline workers started successfully.")

    def stop_all(self):
        """3대 워커 안전 종료"""
        logger.info("WorkerManager: Stopping workers...")
        self.inference_worker.stop()
        self.event_worker.stop()
        self.ingestion_worker.stop()
        logger.info("WorkerManager: All workers stopped.")

    def trigger_once(self):
        """수동 트리거: 링 버퍼의 최신 프레임 1장을 정식 파이프라인(process_frame)으로 처리"""
        frames = self.ingestion_worker.get_recent_frames(1)
        if not frames:
            return None
        return self.inference_worker.process_frame(frames[-1])

    def get_telemetry(self) -> Dict[str, Any]:
        """모바일/대시보드용 실시간 관제 메트릭 집계"""
        return {
            "farm_id": self.profile.farm_id,
            "camera_id": self.profile.primary_camera.camera_id,
            "species": self.profile.rules.species,
            "ingestion_worker": {
                "status": "running" if getattr(self.ingestion_worker, "_running", False) else "stopped",
                "is_connected": getattr(self.ingestion_worker, "is_connected", False),
                "target_fps": getattr(self.ingestion_worker, "target_fps", 0.0),
                "total_captured": getattr(self.ingestion_worker, "total_captured", 0),
                "reconnect_count": getattr(self.ingestion_worker, "reconnect_count", 0),
            },
            "inference_worker": {
                "status": "running" if self.inference_worker._running else "stopped",
                "total_inferences": self.inference_worker.total_inferences,
                "filtered_count": self.inference_worker.filtered_count,
                "event_saved_count": self.inference_worker.event_saved_count,
                "anomaly_count": self.inference_worker.anomaly_count,
                "last_result": self.inference_worker.last_result,
            },
            "event_worker": {
                "status": "running" if self.event_worker._running else "stopped",
                "total_events_received": self.event_worker.total_events_received,
                "total_clips_created": self.event_worker.total_clips_created,
                "total_uploads_completed": getattr(self.event_worker, "total_uploads_completed", 0),
                "total_webhooks_sent": self.event_worker.total_webhooks_sent,
                "total_sheets_recorded": getattr(self.event_worker, "total_sheets_recorded", 0),
                "total_drive_uploads": getattr(self.event_worker, "total_drive_uploads", 0),
                "queue_size": self.event_worker.event_queue.qsize(),
            },
        }


worker_manager = WorkerManager()
