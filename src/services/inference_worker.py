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
from src.services.storage_cleaner import StorageCleaner

logger = logging.getLogger(__name__)

class InferenceWorker:
    """
    독립 AI 추론 전용 Worker (소비자).
    - IngestionWorker의 큐에서 최신 프레임을 꺼내 비동기 처리
    - 일반 프레임은 captures/spool/ (임시 대기소)에 단기 보관 (자동 회전 삭제)
    - 1차: 로컬 Ultralytics YOLO11n 엔진으로 0ms 객체 탐지
    - 2차: 실제 관심 객체(소/사람) 및 이상 징후 포착 시 captures/events/ 폴더로 정식 이관
    - 3차: 이관된 events 파일만 선별하여 Gemini 2.5 Flash API 판독 및 알람 전송
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
        
        # 디렉터리 경로 초기화
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.spool_dir = os.path.join(self.base_dir, "captures", "spool")
        self.events_dir = os.path.join(self.base_dir, "captures", "events")
        os.makedirs(self.spool_dir, exist_ok=True)
        os.makedirs(self.events_dir, exist_ok=True)
        
        # 스토리지 청소기 장착 (spool: 15분 보관, events: 7일 보관, 총 2GB 한도)
        self.cleaner = StorageCleaner(self.base_dir, spool_retention_minutes=15, event_retention_days=7, max_total_mb=2048)
        self.last_cleanup_time = time.time()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 관심 객체 필터 (소: cow, 가축: horse/sheep/dog, 사람: person)
        self.target_classes = {"cow", "horse", "sheep", "dog", "person"}
        
        # Telemetry & Metrics
        self.total_inferences = 0
        self.filtered_count = 0  # 1차 YOLO에서 걸러진 무의미 프레임 수
        self.event_saved_count = 0  # events 폴더로 정식 이관된 파일 수
        self.anomaly_count = 0   # Gemini 이상 징후 감지 횟수
        self.last_result: Optional[Dict[str, Any]] = None

    def start(self):
        """추론 백그라운드 스레드 가동"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="InferenceWorkerThread")
        self._thread.start()
        logger.info("InferenceWorker started. 2-Tier Staging Buffer (spool -> events) active.")

    def stop(self):
        """추론 스레드 안전 종료"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("InferenceWorker stopped safely.")

    def _save_spool_frame(self, frame: np.ndarray) -> str:
        """1차 임시 spool 폴더에 프레임 저장"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"spool_{timestamp}_{int(time.time()*1000)%1000}.jpg"
        filepath = os.path.join(self.spool_dir, filename)
        cv2.imwrite(filepath, frame)
        return filepath

    def _promote_to_event(self, frame: np.ndarray, tag: str = "cow_detected") -> str:
        """관심 객체 포착 시 events 폴더로 정식 영속 이관"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"event_{tag}_{timestamp}_{int(time.time()*1000)%1000}.jpg"
        filepath = os.path.join(self.events_dir, filename)
        cv2.imwrite(filepath, frame)
        self.event_saved_count += 1
        logger.info(f"InferenceWorker: Promoted to event file -> {filepath}")
        return filepath

    def _run_loop(self):
        """핵심 추론 루프: 큐 수신 -> spool 저장 -> 1차 YOLO 필터 -> 이벤트 승격(events) -> 2차 Gemini 전송"""
        while self._running:
            frame = self.ingestion_worker.get_latest_frame(timeout=self.poll_interval)
            if frame is None:
                continue

            self.total_inferences += 1
            
            # 1. 1차 임시 spool 폴더에 단기 기록
            spool_path = self._save_spool_frame(frame)
            
            # 2. 로컬 1차 YOLO 추론 (3500X CPU 42ms 초고속)
            results = self.yolo_model(frame, verbose=False)
            boxes = results[0].boxes
            
            detected_targets = []
            for box in boxes:
                cls_name = self.yolo_model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if cls_name in self.target_classes and conf >= 0.25:
                    detected_targets.append({"label": cls_name, "confidence": round(conf, 2)})

            # 대상(소/사람) 미감지 시: spool에만 남고 events 승격 스킵 (임시 파일은 15분 뒤 자동 청소)
            if not detected_targets:
                self.filtered_count += 1
                self.last_result = {
                    "timestamp": time.time(),
                    "status": "filtered",
                    "reason": "no_target_objects_detected",
                    "spool_frame_path": spool_path,
                    "event_frame_path": None,
                    "yolo_count": 0
                }
            else:
                # 3. 중요 이벤트 발생 시: captures/events/ 로 공식 이관!
                primary_label = detected_targets[0]["label"]
                event_path = self._promote_to_event(frame, tag=primary_label)
                
                # 4. events에 이관된 정선된 프레임만 Gemini AI로 전송 (비용 95% 절감!)
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
                    "status": "event_recorded",
                    "spool_frame_path": spool_path,
                    "event_frame_path": event_path,
                    "yolo_detections": detected_targets,
                    "ai_analysis": ai_analysis.dict() if ai_analysis else None
                }

            # 5. 주기적 디스크 청소 (5분 주기)
            if time.time() - self.last_cleanup_time > 300:
                self.cleaner.run_cleanup_cycle()
                self.last_cleanup_time = time.time()

            time.sleep(self.poll_interval)
