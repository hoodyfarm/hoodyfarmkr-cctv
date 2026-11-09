import os
import time
import logging
import httpx
from typing import Optional, Dict, Any, List
from src.config import settings

logger = logging.getLogger(__name__)

class FMSWebhookClient:
    """
    hoodyfarmkr-fms 연동 전용 Webhook Egress 클라이언트
    """

    def __init__(self, webhook_url: Optional[str] = None, timeout: float = 4.0):
        self.webhook_url = webhook_url or settings.FMS_WEBHOOK_URL
        self.timeout = timeout

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
        oci_frame_url: Optional[str] = None
    ) -> str:
        """
        FMS Webhook 서버로 이벤트 알림, OCI URL 및 생성된 클립 메타데이터 전송
        """
        if not self.webhook_url:
            logger.info("FMSWebhookClient: FMS_WEBHOOK_URL is not configured. Webhook skipped.")
            return "skipped (no url)"

        clip_filename = os.path.basename(clip_path) if clip_path else None
        clip_size_bytes = os.path.getsize(clip_path) if clip_path and os.path.exists(clip_path) else 0

        payload = {
            "event_source": "hoodyfarmkr-cctv",
            "event_id": event_id,
            "event_type": event_type,
            "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "is_anomaly": is_anomaly,
            "detections": detections,
            "clip": {
                "file_name": clip_filename,
                "file_path": clip_path,
                "file_size_bytes": clip_size_bytes,
                "duration_seconds": 6.0,
                "oci_url": oci_clip_url
            } if clip_path else None,
            "frame_path": frame_path,
            "oci_clip_url": oci_clip_url,
            "oci_frame_url": oci_frame_url,
            "summary": ai_summary or f"{event_type} detected by CCTV Pipeline",
            "status": "alert"
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.webhook_url, json=payload)
                if resp.status_code in (200, 201, 202):
                    logger.info(f"FMSWebhookClient: ✅ Webhook delivered ({resp.status_code}) for event [{event_id}]")
                    return f"success ({resp.status_code})"
                else:
                    logger.warning(f"FMSWebhookClient: ⚠️ Webhook response {resp.status_code} for event [{event_id}]")
                    return f"failed ({resp.status_code})"
        except Exception as e:
            logger.warning(f"FMSWebhookClient: ⚠️ Webhook connection error for event [{event_id}]: {e}")
            return f"error ({e})"
