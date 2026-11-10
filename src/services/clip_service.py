import os
import time
import logging
import cv2
import numpy as np
import httpx
from typing import List, Optional, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class ClipService:
    """
    이벤트 전후 프레임 버퍼를 조합하여 MP4 영상 클립 생성 및 FMS Webhook 전송 담당
    """

    def __init__(self, output_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.output_dir = output_dir or os.path.join(base_dir, "captures", "clips")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_mp4_clip(
        self,
        frames: List[np.ndarray],
        tag: str = "event",
        fps: float = 5.0
    ) -> Optional[str]:
        """
        프레임 리스트를 .mp4 영상 파일로 인코딩하여 저장.
        저장 경로 반환 (실패 시 None)
        """
        if not frames:
            logger.warning("ClipService: No frames provided to generate MP4 clip.")
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"clip_{tag}_{timestamp}_{int(time.time() * 1000) % 1000}.mp4"
        filepath = os.path.join(self.output_dir, filename)

        height, width = frames[0].shape[:2]
        
        # mp4v 코덱 사용 (Windows / Linux OpenCV 기본 내장 지원)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filepath, fourcc, float(fps), (width, height))

        if not writer.isOpened():
            logger.error(f"ClipService: Failed to open VideoWriter for {filepath}")
            return None

        try:
            for frame in frames:
                # 프레임 크기가 다를 경우 첫 번째 프레임 크기로 리사이즈
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        except Exception as e:
            logger.error(f"ClipService: Error while writing frames to MP4: {e}")
            return None
        finally:
            writer.release()

        logger.info(f"ClipService: ✅ Successfully generated MP4 clip ({len(frames)} frames, {fps} FPS) -> {filepath}")
        return filepath

    def send_fms_webhook(
        self,
        event_type: str,
        detections: List[Dict[str, Any]],
        clip_path: Optional[str] = None,
        frame_path: Optional[str] = None,
        ai_summary: Optional[str] = None,
        is_anomaly: bool = False,
        webhook_url: Optional[str] = None,
        drive_clip_url: Optional[str] = None,
        drive_image_url: Optional[str] = None,
        tailscale_clip_url: Optional[str] = None,
        tailscale_image_url: Optional[str] = None
    ) -> str:
        """
        FMS Webhook 엔드포인트로 이벤트 메타데이터 및 2-Tier Fallback 클립/이미지 정보 전송 (동기식)
        """
        url = webhook_url or settings.FMS_WEBHOOK_URL
        if not url:
            logger.info("ClipService: FMS_WEBHOOK_URL is not configured. Webhook skipped.")
            return "skipped (no url)"

        clip_filename = os.path.basename(clip_path) if clip_path else None
        clip_size_bytes = os.path.getsize(clip_path) if clip_path and os.path.exists(clip_path) else 0

        ts_base = (settings.TAILSCALE_HOST_URL or "").rstrip("/")
        if ts_base and not tailscale_clip_url and clip_filename:
            tailscale_clip_url = f"{ts_base}/api/v1/pipeline/captures/view/clips/{clip_filename}"

        frame_filename = os.path.basename(frame_path) if frame_path else None
        if ts_base and not tailscale_image_url and frame_filename:
            tailscale_image_url = f"{ts_base}/api/v1/pipeline/captures/view/events/{frame_filename}"

        payload = {
            "event_source": "hoodyfarmkr-cctv",
            "farm_id": settings.FARM_ID,
            "event_type": event_type,
            "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "is_anomaly": is_anomaly,
            "detections": detections,
            "clip": {
                "file_name": clip_filename,
                "file_path": clip_path,
                "file_size_bytes": clip_size_bytes,
                "duration_seconds": 6.0,
                "drive_clip_url": drive_clip_url,
                "tailscale_clip_url": tailscale_clip_url
            } if clip_path else None,
            "frame_path": frame_path,
            "drive_clip_url": drive_clip_url,
            "drive_image_url": drive_image_url,
            "tailscale_clip_url": tailscale_clip_url,
            "tailscale_image_url": tailscale_image_url,
            "video_clip_url": drive_clip_url or tailscale_clip_url,
            "snapshot_url": drive_image_url or tailscale_image_url,
            "summary": ai_summary or f"{event_type} detected by CCTV AI Worker",
            "status": "alert"
        }

        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code in (200, 201, 202):
                    logger.info(f"ClipService: ✅ FMS Webhook delivered successfully ({resp.status_code})")
                    return f"success ({resp.status_code})"
                else:
                    logger.warning(f"ClipService: ⚠️ FMS Webhook responded with status {resp.status_code}")
                    return f"failed ({resp.status_code})"
        except Exception as e:
            logger.warning(f"ClipService: ⚠️ FMS Webhook connection error: {e}")
            return f"error ({e})"
