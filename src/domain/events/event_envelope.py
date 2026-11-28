from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.domain.events.detection_event import DetectionEvent, DetectionTarget


class MediaUrls(BaseModel):
    """
    다계층(Tier 1 Drive / Tier 2 Tailscale / OCI Signed URL) 미디어 URL 및 베스트 폴백 해석 모델.
    """
    drive_clip_url: Optional[str] = None
    drive_image_url: Optional[str] = None
    tailscale_clip_url: Optional[str] = None
    tailscale_image_url: Optional[str] = None
    oci_clip_url: Optional[str] = None
    oci_frame_url: Optional[str] = None
    media_signed_url: Optional[str] = None
    frame_signed_url: Optional[str] = None

    def resolve_clip_url(self, priority: Optional[List[str]] = None) -> Optional[str]:
        # priority support: "signed_url", "drive", "tailscale", "oci"
        order = priority or ["signed_url", "drive", "tailscale", "oci"]
        mapping: Dict[str, Optional[str]] = {
            "signed_url": self.media_signed_url,
            "drive": self.drive_clip_url,
            "tailscale": self.tailscale_clip_url,
            "oci": self.oci_clip_url or self.media_signed_url,
        }
        for tier in order:
            if mapping.get(tier):
                return mapping[tier]
        return self.media_signed_url or self.drive_clip_url or self.tailscale_clip_url or self.oci_clip_url

    def resolve_snapshot_url(self, priority: Optional[List[str]] = None) -> Optional[str]:
        order = priority or ["signed_url", "drive", "tailscale", "oci"]
        mapping: Dict[str, Optional[str]] = {
            "signed_url": self.frame_signed_url,
            "drive": self.drive_image_url,
            "tailscale": self.tailscale_image_url,
            "oci": self.oci_frame_url or self.frame_signed_url,
        }
        for tier in order:
            if mapping.get(tier):
                return mapping[tier]
        return self.frame_signed_url or self.drive_image_url or self.tailscale_image_url or self.oci_frame_url

    @property
    def preferred_clip_url(self) -> Optional[str]:
        return self.resolve_clip_url()


class ClipMeta(BaseModel):
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: int = 0
    duration_seconds: float = 6.0
    oci_url: Optional[str] = None
    drive_clip_url: Optional[str] = None
    tailscale_clip_url: Optional[str] = None


class CCTVEventEnvelopeV1(BaseModel):
    """
    FMS 및 외부 소비자와의 이벤트 계약 v1 (JSON Schema).
    기존 FMS 웹훅 top-level 필드와 100% 하위 호환되면서 schema_version / farm_id / camera_id를 보장합니다.
    """
    schema_version: str = "1.0"
    event_source: str = "hoodyfarmkr-cctv"
    farm_id: str = "default"
    camera_id: str = "default_cctv"
    event_id: str
    event_type: str = "NORMAL"
    event_code: Optional[str] = None
    detected_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    is_anomaly: bool = False
    detections: List[DetectionTarget] = Field(default_factory=list)
    clip: Optional[ClipMeta] = None
    frame_path: Optional[str] = None
    media_signed_url: Optional[str] = None
    frame_signed_url: Optional[str] = None
    media_urls: Optional[MediaUrls] = None
    oci_clip_url: Optional[str] = None
    oci_frame_url: Optional[str] = None
    drive_clip_url: Optional[str] = None
    drive_image_url: Optional[str] = None
    tailscale_clip_url: Optional[str] = None
    tailscale_image_url: Optional[str] = None
    video_clip_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    summary: str = ""
    status: str = "alert"

    @property
    def version(self) -> str:
        return self.schema_version

    @classmethod
    def from_event(
        cls,
        event: DetectionEvent,
        farm_id: str = "default",
        clip_path: Optional[str] = None,
        clip_size_bytes: int = 0,
        clip_filename: Optional[str] = None,
        media: Optional[MediaUrls] = None,
        media_priority: Optional[List[str]] = None,
        media_signed_url: Optional[str] = None,
        frame_signed_url: Optional[str] = None,
    ) -> "CCTVEventEnvelopeV1":
        m = media or MediaUrls()
        if media_signed_url and not m.media_signed_url:
            m.media_signed_url = media_signed_url
        if frame_signed_url and not m.frame_signed_url:
            m.frame_signed_url = frame_signed_url
        
        # If media_signed_url not set but oci_clip_url exists, default it
        if not m.media_signed_url and m.oci_clip_url:
            m.media_signed_url = m.oci_clip_url
        if not m.frame_signed_url and m.oci_frame_url:
            m.frame_signed_url = m.oci_frame_url

        resolved_type = event.event_type or ("ANOMALY" if event.is_anomaly else "NORMAL")
        clip_meta = (
            ClipMeta(
                file_name=clip_filename,
                file_path=clip_path,
                file_size_bytes=clip_size_bytes,
                duration_seconds=round(event.pre_sec + event.post_sec, 2),
                oci_url=m.oci_clip_url or m.media_signed_url,
                drive_clip_url=m.drive_clip_url,
                tailscale_clip_url=m.tailscale_clip_url,
            )
            if clip_path
            else None
        )
        return cls(
            farm_id=farm_id,
            camera_id=event.camera_id,
            event_id=event.event_id,
            event_type=resolved_type,
            event_code=resolved_type,
            is_anomaly=event.is_anomaly,
            detections=list(event.detections),
            clip=clip_meta,
            frame_path=event.frame_path,
            media_signed_url=m.media_signed_url,
            frame_signed_url=m.frame_signed_url,
            media_urls=m,
            oci_clip_url=m.oci_clip_url,
            oci_frame_url=m.oci_frame_url,
            drive_clip_url=m.drive_clip_url,
            drive_image_url=m.drive_image_url,
            tailscale_clip_url=m.tailscale_clip_url,
            tailscale_image_url=m.tailscale_image_url,
            video_clip_url=m.resolve_clip_url(media_priority),
            snapshot_url=m.resolve_snapshot_url(media_priority),
            summary=event.ai_summary or f"{resolved_type} detected by CCTV Pipeline",
            status="alert" if event.is_anomaly else "confirmed",
        )
