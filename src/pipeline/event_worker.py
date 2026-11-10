import os
import time
import queue
import threading
import logging
from typing import Optional, Dict, Any, List

from src.config import settings
from src.core.ports import (
    ClipEncoderPort,
    EventNotifierPort,
    FrameSourcePort,
    ObjectStoragePort,
    WorkspaceSinkPort,
)
from src.domain.events.detection_event import DetectionEvent
from src.domain.events.event_envelope import CCTVEventEnvelopeV1, MediaUrls
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService

logger = logging.getLogger(__name__)


class EventWorker:
    """
    이벤트 전용 비동기 소비자 워커 (Event Worker).
    - InferenceWorker가 발행한 DetectionEvent를 수신
    - 사후 대기(post_sec)를 거쳐 FrameSourcePort 링 버퍼에서 전후 프레임 획득
    - ClipEncoderPort로 MP4 클립 생성
    - ObjectStoragePort(OCI)에 영상 클립 및 스냅샷 업로드
    - WorkspaceSinkPort(Google Drive + Sheets)에 업로드 및 행 추가
    - CCTVEventEnvelopeV1 표준 계약을 조립하여 EventNotifierPort(FMS Webhook)로 발송
    """

    def __init__(
        self,
        ingestion_worker: FrameSourcePort,
        video_encoder: ClipEncoderPort,
        fms_client: Any,
        oci_service: Optional[ObjectStoragePort] = None,
        google_service: Optional[WorkspaceSinkPort] = None,
        max_queue_size: int = 100,
        farm_id: Optional[str] = None,
        tailscale_host_url: Optional[str] = None,
        media_priority: Optional[List[str]] = None,
    ):
        self.ingestion_worker = ingestion_worker
        self.video_encoder = video_encoder
        self.fms_client = fms_client
        self.oci_service = oci_service or OCIDataPipelineService()
        self.google_service = google_service or GoogleIntegrationService()
        self.farm_id = farm_id
        self.tailscale_host_url = tailscale_host_url
        self.media_priority = media_priority or ["drive", "tailscale", "oci"]
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

    def _build_envelope(
        self,
        event: DetectionEvent,
        resolved_event_type: str,
        clip_path: Optional[str],
        oci_clip_url: Optional[str],
        oci_frame_url: Optional[str],
        drive_clip_url: Optional[str],
        drive_image_url: Optional[str],
    ) -> CCTVEventEnvelopeV1:
        ts_raw = self.tailscale_host_url if self.tailscale_host_url is not None else settings.TAILSCALE_HOST_URL
        ts_base = (ts_raw or "").rstrip("/")
        clip_filename = os.path.basename(clip_path) if clip_path else None
        frame_filename = os.path.basename(event.frame_path) if event.frame_path else None
        clip_size_bytes = os.path.getsize(clip_path) if clip_path and os.path.exists(clip_path) else 0

        ts_clip_url = (
            f"{ts_base}/api/v1/pipeline/captures/view/clips/{clip_filename}"
            if (ts_base and clip_filename)
            else None
        )
        ts_image_url = (
            f"{ts_base}/api/v1/pipeline/captures/view/events/{frame_filename}"
            if (ts_base and frame_filename)
            else None
        )
        media = MediaUrls(
            drive_clip_url=drive_clip_url,
            drive_image_url=drive_image_url,
            tailscale_clip_url=ts_clip_url,
            tailscale_image_url=ts_image_url,
            oci_clip_url=oci_clip_url,
            oci_frame_url=oci_frame_url,
        )
        updated_event = event.model_copy(update={"event_type": resolved_event_type})
        return CCTVEventEnvelopeV1.from_event(
            event=updated_event,
            farm_id=self.farm_id or settings.FARM_ID,
            clip_path=clip_path,
            clip_size_bytes=clip_size_bytes,
            clip_filename=clip_filename,
            media=media,
            media_priority=self.media_priority,
        )

    def _dispatch_notification(
        self,
        envelope: CCTVEventEnvelopeV1,
        detections_dict: List[Dict[str, Any]],
        clip_path: Optional[str],
        oci_clip_url: Optional[str],
        oci_frame_url: Optional[str],
        drive_clip_url: Optional[str],
        drive_image_url: Optional[str],
    ) -> str:
        """
        1) 실제 FMSWebhookClient 인스턴스이면 notify(envelope)로 표준 계약 발송
        2) 테스트 Mock이나 레거시 구현체처럼 send_event_alert만 설정된 경우 호환 호출 유지
        """
        if isinstance(self.fms_client, FMSWebhookClient):
            return self.fms_client.notify(envelope)
        if hasattr(self.fms_client, "send_event_alert"):
            return self.fms_client.send_event_alert(
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                detections=detections_dict,
                clip_path=clip_path,
                frame_path=envelope.frame_path,
                ai_summary=envelope.summary,
                is_anomaly=envelope.is_anomaly,
                oci_clip_url=oci_clip_url,
                oci_frame_url=oci_frame_url,
                drive_clip_url=drive_clip_url,
                drive_image_url=drive_image_url,
            )
        if hasattr(self.fms_client, "notify"):
            return self.fms_client.notify(envelope)
        return "skipped (no notifier)"

    def _process_single_event(self, event: DetectionEvent):
        """개별 이벤트 처리: 사후 프레임 축적 대기 -> 클립 생성 -> OCI 업로드 -> 웹훅 발송"""
        try:
            elapsed_since_event = time.time() - event.timestamp
            wait_time = (event.post_sec + 0.3) - elapsed_since_event
            if wait_time > 0:
                time.sleep(wait_time)

            frames = self.ingestion_worker.get_buffered_frames_around(
                event_time=event.timestamp,
                pre_sec=event.pre_sec,
                post_sec=event.post_sec,
            )

            clip_path = None
            if frames:
                clip_fps = getattr(self.ingestion_worker, "target_fps", 5.0)
                clip_path = self.video_encoder.encode_clip(
                    frames=frames,
                    tag=event.tag,
                    fps=clip_fps,
                )
                if clip_path:
                    self.total_clips_created += 1

            oci_clip_url = None
            oci_frame_url = None

            if clip_path:
                try:
                    clip_obj_name = f"clips/{event.tag}/{event.event_id}.mp4"
                    clip_upload_res = self.oci_service.upload_file_to_oci(
                        file_path=clip_path,
                        object_name=clip_obj_name,
                        metadata={"event_id": event.event_id, "tag": event.tag, "type": "clip_mp4"},
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
                        metadata={"event_id": event.event_id, "tag": event.tag, "type": "event_frame"},
                    )
                    oci_frame_url = frame_upload_res.get("oci_url") or frame_upload_res.get("oci_object_url")
                    self.total_uploads_completed += 1
                except Exception as e:
                    logger.warning(f"EventWorker: OCI frame upload error for event [{event.event_id}]: {e}")

            primary_label = event.tag
            max_conf = 0.0
            if event.detections:
                primary_label = event.detections[0].label
                max_conf = max(d.confidence for d in event.detections)

            resolved_event_type = getattr(event, "event_type", None) or (
                "ANOMALY" if event.is_anomaly else "NORMAL"
            )

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
                    event_type=resolved_event_type,
                )
                if google_res and google_res.get("status") == "success":
                    self.total_sheets_recorded += 1
                    drive_clip_url = google_res.get("drive_clip_url")
                    drive_image_url = google_res.get("drive_image_url")
                    if google_res.get("drive_result", {}).get("status") == "success":
                        self.total_drive_uploads += 1
            except Exception as e:
                logger.warning(f"EventWorker: Google integration error for event [{event.event_id}]: {e}")

            envelope = self._build_envelope(
                event=event,
                resolved_event_type=resolved_event_type,
                clip_path=clip_path,
                oci_clip_url=oci_clip_url,
                oci_frame_url=oci_frame_url,
                drive_clip_url=drive_clip_url,
                drive_image_url=drive_image_url,
            )
            detections_dict = [d.model_dump() for d in event.detections]
            res = self._dispatch_notification(
                envelope=envelope,
                detections_dict=detections_dict,
                clip_path=clip_path,
                oci_clip_url=oci_clip_url,
                oci_frame_url=oci_frame_url,
                drive_clip_url=drive_clip_url,
                drive_image_url=drive_image_url,
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
