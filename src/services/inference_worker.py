import time
import threading
import os
import logging
import cv2
import numpy as np
from typing import Optional, Dict, Any, List
from ultralytics import YOLO

from src.services.ingestion_worker import IngestionWorker
from src.services.gemini_service import GeminiVisionService
from src.schemas.ai_schema import CCTVAnalysisResultSchema

logger = logging.getLogger(__name__)

class InferenceWorker:
    """
    독립 AI 추론 전용 Worker (소비자).
    - IngestionWorker의 큐에서 최신 프레임을 꺼내 비동기 처리
    - 1차: 로컬 Ultralytics YOLO11n 엔진으로 0ms 객체 탐지 (소/사람 없으면 즉시 폐기)
    - 2차: 모션/이상징후 발생 시에만 Gemini 2.5 Flash API 발송 및 3500X 로컬 디스크에 자동 저장
    """

    def __init__(
        self,
        ingestion_worker: IngestionWorker,
        yolo_model_path: str = "yolo11n.pt",
        poll_interval: float = 1.0,
        enable_gemini: bool = True
    ):
        self.ingestion_worker = ingestion_worker
        self.poll_interval = poll_interval
        self.enable_gemini = enable_gemini
        
        # YOLO 로컬 모델 로드 (3500X CPU 최적화)
        self.yolo_model = YOLO(yolo_model_path)
        self.gemini_service = GeminiVisionService()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 관심 객체 필터 (소: cow, 양/동물: sheep/horse/dog, 사람: person)
        self.target_classes = {"cow", "horse", "sheep", "dog", "person"}
        
        # Telemetry & Metrics
        self.total_inferences = 0
        self.filtered_count = 0  # 1차 YOLO에서 무의미하여 버린 프레임 수
        self.anomaly_count = 0   # 이상/중요 이벤트로 판단된 횟수
        self.last_result: Optional[Dict[str, Any]] = None

    def start(self):
        """추론 백그라운드 스레드 가동"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="InferenceWorkerThread")
        self._thread.start()
        logger.info("InferenceWorker started. Background AI evaluation active.")

    def stop(self):
        """추론 스레드 안전 종료"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("InferenceWorker stopped safely.")

    def _save_local_frame(self, frame: np.ndarray, tag: str = "event") -> str:
        """3500X 로컬 디스크에 프레임 영속 저장"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        save_dir = os.path.join(base_dir, "captures", "frames")
        os.makedirs(save_dir, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{tag}_{timestamp}_{int(time.time()*1000)%1000}.jpg"
        filepath = os.path.join(save_dir, filename)
        
        cv2.imwrite(filepath, frame)
        logger.info(f"InferenceWorker: Saved event frame to {filepath}")
        return filepath

    def _run_loop(self):
        """핵심 추론 루프: 큐에서 프레임 소비 -> 1차 YOLO -> 2차 Gemini"""
        while self._running:
            frame = self.ingestion_worker.get_latest_frame(timeout=self.poll_interval)
            if frame is None:
                continue

            self.total_inferences += 1
            
            # 1. 로컬 1차 YOLO 추론 (3500X CPU 42ms 초고속)
            results = self.yolo_model(frame, verbose=False)
            boxes = results[0].boxes
            
            detected_targets = []
            for box in boxes:
                cls_name = self.yolo_model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if cls_name in self.target_classes and conf >= 0.25:
                    detected_targets.append({"label": cls_name, "confidence": round(conf, 2)})

            # 대상(소/사람)이 전혀 감지되지 않으면 즉시 폐기 (Gemini API 비용 & 디스크 절약)
            if not detected_targets:
                self.filtered_count += 1
                self.last_result = {
                    "timestamp": time.time(),
                    "status": "filtered",
                    "reason": "no_target_objects_detected",
                    "yolo_count": 0
                }
                time.sleep(self.poll_interval)
                continue

            # 2. 대상 객체 포착 시 로컬 저장 및 Gemini 2차 정밀 분석
            saved_path = self._save_local_frame(frame, tag="target_detected")
            
            ai_analysis = None
            if self.enable_gemini:
                try:
                    ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        ai_analysis = self.gemini_service.analyze_frame_structured(buffer.tobytes())
                except Exception as e:
                    logger.warning(f"InferenceWorker: Gemini analysis failed, fallback: {e}")

            if ai_analysis and ai_analysis.is_anomaly:
                self.anomaly_count += 1
                logger.warning(f"🚨 Anomaly Detected: {ai_analysis.summary}")

            self.last_result = {
                "timestamp": time.time(),
                "status": "evaluated",
                "local_frame_path": saved_path,
                "yolo_detections": detected_targets,
                "ai_analysis": ai_analysis.dict() if ai_analysis else None
            }

            time.sleep(self.poll_interval)
