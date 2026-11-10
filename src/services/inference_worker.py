import time
import threading
import os
import logging
import cv2
import numpy as np
from typing import Optional, Dict, Any, List, Set, Iterable
from ultralytics import YOLO

from src.core.ports import EventPublisherPort, FrameSourcePort, VisionAnalyzerPort
from src.services.gemini_service import GeminiVisionService
from src.services.storage_cleaner import StorageCleaner
from src.services.clip_service import ClipService
from src.config import settings
from src.domain.events.detection_event import DetectionEvent, DetectionTarget

logger = logging.getLogger(__name__)


class InferenceWorker:
    """
    독립 AI 추론 전용 Worker (소비자).
    - FrameSourcePort(IngestionWorker)의 큐에서 최신 프레임을 꺼내 비동기 처리
    - 일반 프레임은 captures/spool/ (임시 대기소)에 단기 보관 (자동 회전 삭제)
    - 1차: 로컬 Ultralytics YOLO11n 엔진으로 0ms 객체 탐지 (target_classes 및 confidence_threshold는 농장 프로파일에서 주입 가능)
    - 2차: 실제 관심 객체 포착 시 captures/events/ 폴더로 정식 이관
    - 3차: 이관된 events 파일만 선별하여 VisionAnalyzerPort(Gemini 2.5 Flash) 판독 및 EventPublisherPort(EventWorker)로 발행
    """

    def __init__(
        self,
        ingestion_worker: FrameSourcePort,
        yolo_model_path: str = "yolo11n.pt",
        poll_interval: float = 1.0,
        enable_gemini: bool = True,
        event_worker: Optional[EventPublisherPort] = None,
        vision_service: Optional[VisionAnalyzerPort] = None,
        camera_id: str = "default_cctv",
        target_classes: Optional[Iterable[str]] = None,
        confidence_threshold: float = 0.25,
        vision_prompt: Optional[str] = None,
        cooldown_sec: Optional[float] = None,
        pre_event_sec: Optional[float] = None,
        post_event_sec: Optional[float] = None,
    ):
        self.ingestion_worker = ingestion_worker
        self.poll_interval = poll_interval
        self.enable_gemini = enable_gemini
        self.event_worker = event_worker
        self.camera_id = camera_id
        self.confidence_threshold = confidence_threshold
        self.vision_prompt = vision_prompt

        # YOLO 로컬 모델 로드 (3500X CPU 최적화)
        self.yolo_model = YOLO(yolo_model_path)
        self.gemini_service: VisionAnalyzerPort = vision_service or GeminiVisionService()

        # 디렉터리 경로 초기화
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.spool_dir = os.path.join(self.base_dir, "captures", "spool")
        self.events_dir = os.path.join(self.base_dir, "captures", "events")
        self.clips_dir = os.path.join(self.base_dir, "captures", "clips")
        os.makedirs(self.spool_dir, exist_ok=True)
        os.makedirs(self.events_dir, exist_ok=True)
        os.makedirs(self.clips_dir, exist_ok=True)

        # 클립 생성 & FMS Webhook 서비스 (레거시 독립 구동 호환용)
        self.clip_service = ClipService(output_dir=self.clips_dir)

        # 스토리지 청소기 장착 (spool: 15분 보관, events/clips: 7일 보관, 총 2GB 한도)
        self.cleaner = StorageCleaner(
            self.base_dir, spool_retention_minutes=15, event_retention_days=7, max_total_mb=2048
        )
        self.last_cleanup_time = time.time()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._infer_lock = threading.Lock()

        # 관심 객체 필터 (농장 프로파일에서 주입하거나 기본 가축/사람 세트 사용)
        self.target_classes: Set[str] = (
            set(target_classes) if target_classes is not None else {"cow", "person", "horse", "sheep", "dog"}
        )

        # 이벤트 쿨다운 타이머 (동일 객체 중복 클립 생성 및 웹훅 폭주 방지)
        self.last_event_time = 0.0
        self.event_cooldown_sec = (
            cooldown_sec if cooldown_sec is not None else getattr(settings, "EVENT_COOLDOWN_SEC", 10.0)
        )
        self.pre_event_sec = (
            pre_event_sec if pre_event_sec is not None else getattr(settings, "CLIP_PRE_EVENT_SEC", 3.0)
        )
        self.post_event_sec = (
            post_event_sec if post_event_sec is not None else getattr(settings, "CLIP_POST_EVENT_SEC", 3.0)
        )

        # Telemetry & Metrics
        self.total_inferences = 0
        self.filtered_count = 0
        self.event_saved_count = 0
        self.clips_generated_count = 0
        self.webhook_sent_count = 0
        self.anomaly_count = 0
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

    def _process_event_clip_and_webhook(
        self,
        event_time: float,
        tag: str,
        detected_targets: List[Dict[str, Any]],
        event_frame_path: str,
        ai_analysis: Any,
    ):
        """
        비동기 스레드에서 사후(post_event_sec) 경과 대기 후
        사전 3초 ~ 사후 3초 프레임을 모아 MP4 비디오 클립 생성 및 FMS Webhook 전송
        """
        try:
            time.sleep(self.post_event_sec + 0.5)

            frames = self.ingestion_worker.get_buffered_frames_around(
                event_time=event_time,
                pre_sec=self.pre_event_sec,
                post_sec=self.post_event_sec,
            )

            clip_path = None
            if frames:
                clip_fps = getattr(self.ingestion_worker, "target_fps", 5.0)
                clip_path = self.clip_service.generate_mp4_clip(
                    frames=frames,
                    tag=tag,
                    fps=clip_fps,
                )
                if clip_path:
                    self.clips_generated_count += 1

            is_anomaly = bool(ai_analysis and ai_analysis.is_anomaly)
            event_type = (
                ai_analysis.event_type
                if (ai_analysis and hasattr(ai_analysis, "event_type"))
                else ("ANOMALY" if is_anomaly else "NORMAL")
            )
            summary = ai_analysis.summary if ai_analysis else f"{tag} detected at CCTV"
            webhook_res = self.clip_service.send_fms_webhook(
                event_type=event_type,
                detections=detected_targets,
                clip_path=clip_path,
                frame_path=event_frame_path,
                ai_summary=summary,
                is_anomaly=is_anomaly,
            )
            if "success" in webhook_res:
                self.webhook_sent_count += 1

            logger.info(f"InferenceWorker: [Event Completed] Clip: {clip_path}, FMS Webhook: {webhook_res}")
        except Exception as e:
            logger.error(f"InferenceWorker: Failed to process event clip and webhook: {e}")

    def process_frame(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """단일 프레임 처리: spool 저장 -> YOLO 필터 -> 이벤트 승격 -> Gemini -> EventWorker 발행. 루프/수동 트리거 공용."""
        with self._infer_lock:
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
                if cls_name in self.target_classes and conf >= self.confidence_threshold:
                    detected_targets.append({"label": cls_name, "confidence": round(conf, 2)})

            if not detected_targets:
                self.filtered_count += 1
                self.last_result = {
                    "timestamp": time.time(),
                    "status": "filtered",
                    "reason": "no_target_objects_detected",
                    "spool_frame_path": spool_path,
                    "event_frame_path": None,
                    "yolo_count": 0,
                }
            else:
                # 3. 중요 이벤트 발생 시: captures/events/ 로 공식 이관
                primary_label = detected_targets[0]["label"]
                event_path = self._promote_to_event(frame, tag=primary_label)

                # 4. events에 이관된 정선된 프레임만 Gemini AI로 전송
                ai_analysis = None
                if self.enable_gemini:
                    try:
                        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ret:
                            ai_analysis = self.gemini_service.analyze_frame_structured(
                                buffer.tobytes(), custom_prompt=self.vision_prompt
                            )
                    except Exception as e:
                        logger.warning(f"InferenceWorker: Gemini analysis failed, fallback: {e}")

                if ai_analysis and ai_analysis.is_anomaly:
                    self.anomaly_count += 1
                    logger.warning(f"Anomaly Detected: {ai_analysis.summary}")

                # 5. EventWorker로 비동기 이벤트 발행 (Zero-Blocking)
                now = time.time()
                clip_status = "cooldown"

                if now - self.last_event_time >= self.event_cooldown_sec:
                    self.last_event_time = now
                    clip_status = "processing"

                    event_id = f"evt_{int(now * 1000)}"
                    targets = [
                        DetectionTarget(label=d["label"], confidence=d["confidence"])
                        for d in detected_targets
                    ]
                    resolved_event_type = (
                        ai_analysis.event_type
                        if (ai_analysis and hasattr(ai_analysis, "event_type"))
                        else ("ANOMALY" if (ai_analysis and ai_analysis.is_anomaly) else "NORMAL")
                    )
                    detection_event = DetectionEvent(
                        event_id=event_id,
                        camera_id=self.camera_id,
                        tag=primary_label,
                        event_type=resolved_event_type,
                        timestamp=now,
                        detections=targets,
                        frame_path=event_path,
                        is_anomaly=bool(ai_analysis and ai_analysis.is_anomaly),
                        ai_summary=ai_analysis.summary if ai_analysis else None,
                        pre_sec=self.pre_event_sec,
                        post_sec=self.post_event_sec,
                    )

                    if self.event_worker is not None:
                        self.event_worker.publish_event(detection_event)
                    else:
                        threading.Thread(
                            target=self._process_event_clip_and_webhook,
                            args=(now, primary_label, detected_targets, event_path, ai_analysis),
                            daemon=True,
                            name=f"ClipWebhookWorker-{int(now)}",
                        ).start()

                self.last_result = {
                    "timestamp": now,
                    "status": "event_recorded",
                    "spool_frame_path": spool_path,
                    "event_frame_path": event_path,
                    "clip_status": clip_status,
                    "yolo_detections": detected_targets,
                    "ai_analysis": ai_analysis.model_dump() if ai_analysis else None,
                }
            return self.last_result

    def _run_loop(self):
        """핵심 추론 루프: 큐 수신 -> process_frame -> 주기적 청소"""
        while self._running:
            frame = self.ingestion_worker.get_latest_frame(timeout=self.poll_interval)
            if frame is None:
                continue
            self.process_frame(frame)

            # 5. 주기적 디스크 청소 (5분 주기)
            if time.time() - self.last_cleanup_time > 300:
                self.cleaner.run_cleanup_cycle()
                self.last_cleanup_time = time.time()

            time.sleep(self.poll_interval)
