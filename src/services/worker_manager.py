import os
import logging
from src.config import settings
from src.services.ingestion_worker import IngestionWorker
from src.services.inference_worker import InferenceWorker
from src.pipeline.event_worker import EventWorker
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService

logger = logging.getLogger(__name__)

class WorkerManager:
    """
    3-Worker (IngestionWorker + InferenceWorker + EventWorker) 글로벌 라이프사이클 관리 싱글톤
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WorkerManager, cls).__new__(cls)
            
            # Base directories
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            clips_dir = os.path.join(base_dir, "captures", "clips")
            
            # Infrastructure components
            cls._instance.video_encoder = VideoEncoder(output_dir=clips_dir)
            cls._instance.fms_client = FMSWebhookClient(webhook_url=settings.FMS_WEBHOOK_URL)
            cls._instance.oci_service = OCIDataPipelineService()
            cls._instance.google_service = GoogleIntegrationService()
            
            # Ingestion Worker
            cls._instance.ingestion_worker = IngestionWorker(
                stream_url=settings.RTSP_STREAM_URL,
                target_fps=getattr(settings, "CLIP_FPS", 5.0),
                max_queue_size=1,
                ring_buffer_sec=10.0
            )
            
            # Event Worker (Clip creation, OCI upload & Webhook dispatching)
            cls._instance.event_worker = EventWorker(
                ingestion_worker=cls._instance.ingestion_worker,
                video_encoder=cls._instance.video_encoder,
                fms_client=cls._instance.fms_client,
                oci_service=cls._instance.oci_service,
                google_service=cls._instance.google_service
            )
            
            # Inference Worker (AI Detection & Event publishing)
            cls._instance.inference_worker = InferenceWorker(
                ingestion_worker=cls._instance.ingestion_worker,
                yolo_model_path="yolo11n.pt",
                poll_interval=1.0,
                enable_gemini=bool(settings.GEMINI_API_KEY and "your_" not in settings.GEMINI_API_KEY),
                event_worker=cls._instance.event_worker
            )
        return cls._instance

    def start_all(self):
        """3대 워커 백그라운드 스레드 가동"""
        logger.info("WorkerManager: Starting IngestionWorker, EventWorker, and InferenceWorker...")
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

    def get_telemetry(self):
        """모바일/대시보드용 실시간 관제 메트릭 집계"""
        return {
            "ingestion_worker": {
                "status": "running" if self.ingestion_worker._running else "stopped",
                "is_connected": self.ingestion_worker.is_connected,
                "target_fps": self.ingestion_worker.target_fps,
                "total_captured": self.ingestion_worker.total_captured,
                "reconnect_count": self.ingestion_worker.reconnect_count,
            },
            "inference_worker": {
                "status": "running" if self.inference_worker._running else "stopped",
                "total_inferences": self.inference_worker.total_inferences,
                "filtered_count": self.inference_worker.filtered_count,
                "event_saved_count": self.inference_worker.event_saved_count,
                "anomaly_count": self.inference_worker.anomaly_count,
                "last_result": self.inference_worker.last_result
            },
            "event_worker": {
                "status": "running" if self.event_worker._running else "stopped",
                "total_events_received": self.event_worker.total_events_received,
                "total_clips_created": self.event_worker.total_clips_created,
                "total_uploads_completed": getattr(self.event_worker, "total_uploads_completed", 0),
                "total_webhooks_sent": self.event_worker.total_webhooks_sent,
                "total_sheets_recorded": getattr(self.event_worker, "total_sheets_recorded", 0),
                "total_drive_uploads": getattr(self.event_worker, "total_drive_uploads", 0),
                "queue_size": self.event_worker.event_queue.qsize()
            }
        }

worker_manager = WorkerManager()
