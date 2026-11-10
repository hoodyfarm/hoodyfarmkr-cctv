import os
import logging
import httpx
from typing import Optional, Dict, Any, List
from src.config import settings
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.domain.events.event_envelope import CCTVEventEnvelopeV1, MediaUrls

logger = logging.getLogger(__name__)


class FMSWebhookClient:
    """
    FMS 연동 전용 Webhook Egress 어댑터 (EventNotifierPort 구현체).
    - 정식 계약 메서드: notify(envelope: CCTVEventEnvelopeV1) -> str
    - 레거시 호환 메서드: send_event_alert(...) -> 내부에서 CCTVEventEnvelopeV1을 조립해 notify() 호출
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: float = 4.0,
        farm_id: Optional[str] = None,
        tailscale_host_url: Optional[str] = None,
        media_priority: Optional[List[str]] = None,
    ):
        self.webhook_url = webhook_url if webhook_url is not None else settings.FMS_WEBHOOK_URL
        self.timeout = timeout
        self.farm_id = farm_id
        self.tailscale_host_url = tailscale_host_url
        self.media_priority = media_priority or ["drive", "tailscale", "oci"]

    def _resolve_tailscale_urls(
        self,
        clip_path: Optional[str],
        frame_path: Optional[str],
        tailscale_clip_url: Optional[str] = None,
        tailscale_image_url: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        ts_raw = self.tailscale_host_url if self.tailscale_host_url is not None else settings.TAILSCALE_HOST_URL
        ts_base = (ts_raw or "").rstrip("/")
        clip_filename = os.path.basename(clip_path) if clip_path else None
        frame_filename = os.path.basename(frame_path) if frame_path else None

        if ts_base and not tailscale_clip_url and clip_filename:
            tailscale_clip_url = f"{ts_base}/api/v1/pipeline/captures/view/clips/{clip_filename}"
        if ts_base and not tailscale_image_url and frame_filename:
            tailscale_image_url = f"{ts_base}/api/v1/pipeline/captures/view/events/{frame_filename}"
        return tailscale_clip_url, tailscale_image_url

    def build_envelope(
        self,
        event: DetectionEvent,
        clip_path: Optional[str] = None,
        oci_clip_url: Optional[str] = None,
        oci_frame_url: Optional[str] = None,
        drive_clip_url: Optional[str] = None,
        drive_image_url: Optional[str] = None,
        tailscale_clip_url: Optional[str] = None,
        tailscale_image_url: Optional[str] = None,
    ) -> CCTVEventEnvelopeV1:
        ts_clip, ts_img = self._resolve_tailscale_urls(
            clip_path=clip_path,
            frame_path=event.frame_path,
            tailscale_clip_url=tailscale_clip_url,
            tailscale_image_url=tailscale_image_url,
        )
        clip_filename = os.path.basename(clip_path) if clip_path else None
        clip_size_bytes = os.path.getsize(clip_path) if clip_path and os.path.exists(clip_path) else 0
        media = MediaUrls(
            drive_clip_url=drive_clip_url,
            drive_image_url=drive_image_url,
            tailscale_clip_url=ts_clip,
            tailscale_image_url=ts_img,
            oci_clip_url=oci_clip_url,
            oci_frame_url=oci_frame_url,
        )
        return CCTVEventEnvelopeV1.from_event(
            event=event,
            farm_id=self.farm_id or settings.FARM_ID,
            clip_path=clip_path,
            clip_size_bytes=clip_size_bytes,
            clip_filename=clip_filename,
            media=media,
            media_priority=self.media_priority,
        )

    def notify(self, envelope: CCTVEventEnvelopeV1) -> str:
        """
        EventNotifierPort 표준 계약 메서드: CCTVEventEnvelopeV1 JSON 스키마를 FMS Webhook으로 전송.
        """
        url = self.webhook_url or settings.FMS_WEBHOOK_URL
        if not url:
            logger.info("FMSWebhookClient: FMS_WEBHOOK_URL is not configured. Webhook skipped.")
            return "skipped (no url)"

        payload = envelope.model_dump()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code in (200, 201, 202):
                    logger.info(
                        f"FMSWebhookClient: Webhook delivered ({resp.status_code}) for event [{envelope.event_id}]"
                    )
                    return f"success ({resp.status_code})"
                logger.warning(
                    f"FMSWebhookClient: Webhook response {resp.status_code} for event [{envelope.event_id}]"
                )
                return f"failed ({resp.status_code})"
        except Exception as e:
            logger.warning(f"FMSWebhookClient: Webhook connection error for event [{envelope.event_id}]: {e}")
            return f"error ({e})"

    def send_event_alert(
        self,
        event_id: str,
        event_type: str,
        detections: List[Dict[str, Any]],
        clip_path: Optional[str] = None,
        frame_path: Optional[str] = None,
        ai_summary: Optional[str] = None,
        is_anomaly: bool = False,
        oci_clip_url: Optional[str] = None,
        oci_frame_url: Optional[str] = None,
        drive_clip_url: Optional[str] = None,
        drive_image_url: Optional[str] = None,
        tailscale_clip_url: Optional[str] = None,
        tailscale_image_url: Optional[str] = None,
        camera_id: str = "default_cctv",
    ) -> str:
        """
        하위 호환용 메서드: 개별 인자를 받아 CCTVEventEnvelopeV1을 생성한 뒤 notify()를 호출합니다.
        """
        targets = [
            d if isinstance(d, DetectionTarget) else DetectionTarget(**d)
            for d in (detections or [])
        ]
        event = DetectionEvent(
            event_id=event_id,
            camera_id=camera_id,
            tag=targets[0].label if targets else "event",
            event_type=event_type,
            detections=targets,
            frame_path=frame_path or "",
            is_anomaly=is_anomaly,
            ai_summary=ai_summary,
        )
        envelope = self.build_envelope(
            event=event,
            clip_path=clip_path,
            oci_clip_url=oci_clip_url,
            oci_frame_url=oci_frame_url,
            drive_clip_url=drive_clip_url,
            drive_image_url=drive_image_url,
            tailscale_clip_url=tailscale_clip_url,
            tailscale_image_url=tailscale_image_url,
        )
        return self.notify(envelope)
