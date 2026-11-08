import logging
from src.config import settings
from src.services.ingestion_worker import IngestionWorker
from src.services.inference_worker import InferenceWorker

logger = logging.getLogger(__name__)

class WorkerManager:
    """
    2-Worker (IngestionWorker + InferenceWorker) 글로벌 라이프사이클 관리 싱글톤
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WorkerManager, cls).__new__(cls)
            cls._instance.ingestion_worker = IngestionWorker(
                stream_url=settings.RTSP_STREAM_URL,
                target_fps=1.5,
                max_queue_size=1
            )
            cls._instance.inference_worker = InferenceWorker(
                ingestion_worker=cls._instance.ingestion_worker,
                yolo_model_path="yolo11n.pt",
                poll_interval=1.0,
                enable_gemini=bool(settings.GEMINI_API_KEY and "your_" not in settings.GEMINI_API_KEY)
            )
        return cls._instance

    def start_all(self):
        """2대 워커 백그라운드 스레드 가동"""
        logger.info("WorkerManager: Starting IngestionWorker and InferenceWorker...")
        self.ingestion_worker.start()
        self.inference_worker.start()
        logger.info("WorkerManager: Both workers started successfully.")

    def stop_all(self):
        """2대 워커 안전 종료"""
        logger.info("WorkerManager: Stopping workers...")
        self.inference_worker.stop()
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
                "anomaly_count": self.inference_worker.anomaly_count,
                "last_result": self.inference_worker.last_result
            }
        }

worker_manager = WorkerManager()
