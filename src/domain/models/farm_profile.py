import os
import re
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate_env(value: Any) -> Any:
    """Recursively expand ${VAR} and ${VAR:-default} in strings loaded from YAML."""
    if isinstance(value, str):
        def _repl(match: re.Match) -> str:
            var_name = match.group(1)
            default_val = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None and env_val != "":
                return env_val
            return default_val if default_val is not None else ""
        return _ENV_PATTERN.sub(_repl, value)
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    return value


class CameraProfile(BaseModel):
    camera_id: str = "cam_01"
    name: str = "Main CCTV"
    zone: str = "default"
    rtsp_url: str = ""
    target_fps: float = 5.0
    ring_buffer_sec: float = 10.0
    enabled: bool = True


class DetectionRulesProfile(BaseModel):
    species: str = "cattle"
    target_classes: List[str] = Field(
        default_factory=lambda: ["cow", "person", "horse", "sheep", "dog"]
    )
    confidence_threshold: float = 0.25
    event_codes: List[str] = Field(
        default_factory=lambda: [
            "INVERTED",
            "CALVING",
            "ESCAPE",
            "ESTRUS",
            "FIGHTING",
            "INTRUSION",
            "FIRE",
            "NORMAL",
        ]
    )
    cooldown_sec: float = 10.0
    pre_event_sec: float = 3.0
    post_event_sec: float = 3.0
    vision_prompt: Optional[str] = None

    def build_vision_prompt(self) -> str:
        if self.vision_prompt:
            return self.vision_prompt
        codes_str = ", ".join(f"'{c}'" for c in self.event_codes)
        return (
            f"Analyze this CCTV camera frame carefully for a {self.species} farm. "
            f"Detect target objects ({', '.join(self.target_classes)}) and identify behavior or anomalies. "
            f"Classify event_type strictly into one of: {codes_str}. "
            "Provide the output strictly matching the required JSON schema with summary in Korean."
        )


class StorageProfile(BaseModel):
    media_priority: List[str] = Field(default_factory=lambda: ["drive", "tailscale", "oci"])
    spool_retention_minutes: int = 15
    event_retention_days: int = 7
    max_total_mb: int = 2048


class NotificationProfile(BaseModel):
    fms_webhook_url: Optional[str] = None
    tailscale_host_url: Optional[str] = None
    timeout_sec: float = 4.0


class FarmProfile(BaseModel):
    """
    농장/사이트 단위 이식형 설정 프로파일 (YAML 또는 Settings에서 로드).
    코드 변경 없이 다른 농장이나 다른 축종/카메라 구성을 주입합니다.
    """
    farm_id: str = "default"
    farm_name: str = "Default Farm"
    cameras: List[CameraProfile] = Field(default_factory=lambda: [CameraProfile()])
    rules: DetectionRulesProfile = Field(default_factory=DetectionRulesProfile)
    storage: StorageProfile = Field(default_factory=StorageProfile)
    notification: NotificationProfile = Field(default_factory=NotificationProfile)

    @property
    def primary_camera(self) -> CameraProfile:
        enabled = [c for c in self.cameras if c.enabled]
        if enabled:
            return enabled[0]
        if self.cameras:
            return self.cameras[0]
        return CameraProfile()

    @classmethod
    def from_yaml(cls, path: str) -> "FarmProfile":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        expanded = _interpolate_env(raw)
        return cls.model_validate(expanded)

    @classmethod
    def from_settings(cls, settings_obj: Any) -> "FarmProfile":
        profile_path = getattr(settings_obj, "FARM_PROFILE_PATH", None)
        if profile_path and os.path.exists(profile_path):
            profile = cls.from_yaml(profile_path)
            # Fill missing runtime values from settings if not specified in YAML
            if not profile.primary_camera.rtsp_url and getattr(settings_obj, "RTSP_STREAM_URL", ""):
                profile.primary_camera.rtsp_url = settings_obj.RTSP_STREAM_URL
            if not profile.notification.fms_webhook_url and getattr(settings_obj, "FMS_WEBHOOK_URL", None):
                profile.notification.fms_webhook_url = settings_obj.FMS_WEBHOOK_URL
            if not profile.notification.tailscale_host_url and getattr(settings_obj, "TAILSCALE_HOST_URL", None):
                profile.notification.tailscale_host_url = settings_obj.TAILSCALE_HOST_URL
            return profile

        return cls(
            farm_id=getattr(settings_obj, "FARM_ID", "default"),
            farm_name=getattr(settings_obj, "APP_NAME", "hoodyfarmkr-cctv"),
            cameras=[
                CameraProfile(
                    camera_id="cam_01",
                    name="Primary CCTV",
                    rtsp_url=getattr(settings_obj, "RTSP_STREAM_URL", ""),
                    target_fps=getattr(settings_obj, "CLIP_FPS", 5.0),
                )
            ],
            rules=DetectionRulesProfile(
                cooldown_sec=getattr(settings_obj, "EVENT_COOLDOWN_SEC", 10.0),
                pre_event_sec=getattr(settings_obj, "CLIP_PRE_EVENT_SEC", 3.0),
                post_event_sec=getattr(settings_obj, "CLIP_POST_EVENT_SEC", 3.0),
            ),
            notification=NotificationProfile(
                fms_webhook_url=getattr(settings_obj, "FMS_WEBHOOK_URL", None),
                tailscale_host_url=getattr(settings_obj, "TAILSCALE_HOST_URL", None),
            ),
        )
