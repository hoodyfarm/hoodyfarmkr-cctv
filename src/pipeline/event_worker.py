import time
import queue
import threading
import logging
from typing import Optional, Dict, Any

from src.domain.events.detection_event import DetectionEvent
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient

logger = logging.getLogger(__name__)

class EventWorker:
    """
    이벤트 전용 비동기 소비자 워커 (Event Worker).
    - InferenceWorker가 발행한 DetectionEvent를 수신
    - 사후 대기(post_sec)를 거쳐 링 버퍼에서 3초 전후 프레임 획득
    - VideoEncoder로 MP4 클립 생성
    - FMSWebhookClient로 비동기 전송
    - AI 추론 파이프라인의 실시간성을 100% 보장 (Zero-Blocking)
    """

    def __init__(
        self,
        ingestion_worker: Any,
        video_encoder: VideoEncoder,
        fms_client: FMSWebhookClient,
        max_queue_size: int = 100
    ):
        self.ingestion_worker = ingestion_worker
        self.video_encoder = video_encoder
        self.fms_client = fms_client
        self.event_queue: queue.Queue[DetectionEvent] = queue.Queue(maxsize=max_queue_size)
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Telemetry
        self.total_events_received = 0
        self.total_clips_created = 0
        self.total_webhooks_sent = 0

    def start(self):
        """이벤트 처리 백그라운드 스레드 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="EventWorkerThread")
        self._thread.start()
        logger.info("EventWorker started. Decoupled clip generation & webhook dispatching active.")

    def stop(self):
        """이벤트 워커 안전 종료"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("EventWorker stopped safely.")

    def publish_event(self, event: DetectionEvent) -> bool:
        """외부/InferenceWorker가 이벤트를 큐에 넣는 메서드 (Non-blocking)"""
        try:
            self.event_queue.put_nowait(event)
            self.total_events_received += 1
            return True
        except queue.Full:
            logger.warning(f"EventWorker: Event queue full! Dropped event [{event.event_id}]")
            return False

    def _run_loop(self):
        while self._running:
            try:
                event = self.event_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._process_single_event(event)

    def _process_single_event(self, event: DetectionEvent):
        """개별 이벤트 처리: 사후 프레임 축적 대기 -> 클립 생성 -> 웹훅 발송"""
        try:
            # 사후 버퍼링 대기 (post_sec 동안 최신 프레임이 링버퍼에 들어올 때까지 대기)
            elapsed_since_event = time.time() - event.timestamp
            wait_time = (event.post_sec + 0.3) - elapsed_since_event
            if wait_time > 0:
                time.sleep(wait_time)

            # 링 버퍼에서 3초 전후 프레임 조회
            frames = self.ingestion_worker.get_buffered_frames_around(
                event_time=event.timestamp,
                pre_sec=event.pre_sec,
                post_sec=event.post_sec
            )

            clip_path = None
            if frames:
                clip_fps = getattr(self.ingestion_worker, "target_fps", 5.0)
                clip_path = self.video_encoder.encode_clip(
                    frames=frames,
                    tag=event.tag,
                    fps=clip_fps
                )
                if clip_path:
                    self.total_clips_created += 1

            # FMS Webhook 전송
            detections_dict = [d.model_dump() for d in event.detections]
            res = self.fms_client.send_event_alert(
                event_id=event.event_id,
                event_type=f"{event.tag}_detected",
                detections=detections_dict,
                clip_path=clip_path,
                frame_path=event.frame_path,
                ai_summary=event.ai_summary,
                is_anomaly=event.is_anomaly
            )

            if "success" in res:
                self.total_webhooks_sent += 1

            logger.info(f"EventWorker: Processed event [{event.event_id}] -> Clip: {clip_path}, Webhook: {res}")
        except Exception as e:
            logger.error(f"EventWorker: Error processing event [{event.event_id}]: {e}")
