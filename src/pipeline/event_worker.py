import time
import queue
import threading
import logging
from typing import Optional, Dict, Any

from src.domain.events.detection_event import DetectionEvent
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService

logger = logging.getLogger(__name__)

class EventWorker:
    """
    이벤트 전용 비동기 소비자 워커 (Event Worker).
    - InferenceWorker가 발행한 DetectionEvent를 수신
    - 사후 대기(post_sec)를 거쳐 링 버퍼에서 3초 전후 프레임 획득
    - VideoEncoder로 MP4 클립 생성
    - OCI Object Storage에 .mp4 영상 클립 및 스냅샷(.jpg) 자동 업로드
    - Google Drive 영상 업로드 및 FMS Google Spreadsheet 자동 행(Row) 추가
    - FMSWebhookClient로 oci_clip_url 포함하여 비동기 전송 (Webhook + Sheets 이중화)
    - AI 추론 파이프라인의 실시간성을 100% 보장 (Zero-Blocking)
    """

    def __init__(
        self,
        ingestion_worker: Any,
        video_encoder: VideoEncoder,
        fms_client: FMSWebhookClient,
        oci_service: Optional[OCIDataPipelineService] = None,
        google_service: Optional[GoogleIntegrationService] = None,
        max_queue_size: int = 100
    ):
        self.ingestion_worker = ingestion_worker
        self.video_encoder = video_encoder
        self.fms_client = fms_client
        self.oci_service = oci_service or OCIDataPipelineService()
        self.google_service = google_service or GoogleIntegrationService()
        self.event_queue: queue.Queue[DetectionEvent] = queue.Queue(maxsize=max_queue_size)
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Telemetry
        self.total_events_received = 0
        self.total_clips_created = 0
        self.total_uploads_completed = 0
        self.total_webhooks_sent = 0
        self.total_sheets_recorded = 0
        self.total_drive_uploads = 0

    def start(self):
        """이벤트 처리 백그라운드 스레드 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="EventWorkerThread")
        self._thread.start()
        logger.info("EventWorker started. Decoupled clip generation, OCI upload & webhook dispatching active.")

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
        """개별 이벤트 처리: 사후 프레임 축적 대기 -> 클립 생성 -> OCI 업로드 -> 웹훅 발송"""
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

            # OCI Object Storage 클라우드 자동 업로드 (영상 클립 & 이벤트 스냅샷)
            oci_clip_url = None
            oci_frame_url = None

            if clip_path:
                try:
                    clip_obj_name = f"clips/{event.tag}/{event.event_id}.mp4"
                    clip_upload_res = self.oci_service.upload_file_to_oci(
                        file_path=clip_path,
                        object_name=clip_obj_name,
                        metadata={"event_id": event.event_id, "tag": event.tag, "type": "clip_mp4"}
                    )
                    oci_clip_url = clip_upload_res.get("oci_url") or clip_upload_res.get("oci_object_url")
                    self.total_uploads_completed += 1
                except Exception as e:
                    logger.warning(f"EventWorker: OCI clip upload error for event [{event.event_id}]: {e}")

            if event.frame_path:
                try:
                    frame_obj_name = f"events/{event.tag}/{event.event_id}.jpg"
                    frame_upload_res = self.oci_service.upload_file_to_oci(
                        file_path=event.frame_path,
                        object_name=frame_obj_name,
                        metadata={"event_id": event.event_id, "tag": event.tag, "type": "event_frame"}
                    )
                    oci_frame_url = frame_upload_res.get("oci_url") or frame_upload_res.get("oci_object_url")
                    self.total_uploads_completed += 1
                except Exception as e:
                    logger.warning(f"EventWorker: OCI frame upload error for event [{event.event_id}]: {e}")

            # Google Drive 업로드 및 FMS Google Spreadsheet 자동 기록 (FMS 연동 이중화)
            primary_label = event.tag
            max_conf = 0.0
            if event.detections:
                primary_label = event.detections[0].label
                max_conf = max(d.confidence for d in event.detections)

            # event_type 단독 필드 결정 (INVERTED, CALVING, ESCAPE, ESTRUS, NORMAL 등)
            resolved_event_type = getattr(event, "event_type", None) or ("ANOMALY" if event.is_anomaly else "NORMAL")

            google_res = None
            drive_clip_url = None
            drive_image_url = None
            try:
                google_res = self.google_service.process_event_record(
                    event_id=event.event_id,
                    camera_id=event.camera_id,
                    detected_object=primary_label,
                    confidence=max_conf,
                    ai_summary=event.ai_summary,
                    clip_path=clip_path,
                    frame_path=event.frame_path,
                    oci_clip_url=oci_clip_url,
                    timestamp=event.timestamp,
                    status="ALERT" if event.is_anomaly else "CONFIRMED",
                    event_type=resolved_event_type
                )
                if google_res and google_res.get("status") == "success":
                    self.total_sheets_recorded += 1
                    drive_clip_url = google_res.get("drive_clip_url")
                    drive_image_url = google_res.get("drive_image_url")
                    if google_res.get("drive_result", {}).get("status") == "success":
                        self.total_drive_uploads += 1
            except Exception as e:
                logger.warning(f"EventWorker: Google integration error for event [{event.event_id}]: {e}")

            # FMS Webhook 전송 (2-Tier Fallback: Tier 1 Drive, Tier 2 Tailscale)
            detections_dict = [d.model_dump() for d in event.detections]
            res = self.fms_client.send_event_alert(
                event_id=event.event_id,
                event_type=resolved_event_type,
                detections=detections_dict,
                clip_path=clip_path,
                frame_path=event.frame_path,
                ai_summary=event.ai_summary,
                is_anomaly=event.is_anomaly,
                oci_clip_url=oci_clip_url,
                oci_frame_url=oci_frame_url,
                drive_clip_url=drive_clip_url,
                drive_image_url=drive_image_url
            )

            if "success" in res:
                self.total_webhooks_sent += 1

            logger.info(
                f"EventWorker: Processed event [{event.event_id}] -> Clip: {clip_path}, "
                f"OCI Clip URL: {oci_clip_url}, Webhook: {res}, "
                f"Google: {google_res.get('status') if google_res else 'none'}"
            )
        except Exception as e:
            logger.error(f"EventWorker: Error processing event [{event.event_id}]: {e}")
