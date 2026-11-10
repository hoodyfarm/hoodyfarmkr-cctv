from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App General Settings
    APP_NAME: str = "hoodyfarmkr-cctv"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Farm / Site Identity (multi-farm portability: events are tagged with this id)
    FARM_ID: str = "default"

    # API Security (X-API-Key header). Mandatory when ENVIRONMENT=production.
    API_KEY: Optional[str] = None
    # Comma-separated allowed CORS origins. Empty = no cross-origin access.
    CORS_ALLOW_ORIGINS: str = ""

    # Local YOLO detector model
    YOLO_MODEL_PATH: str = "yolo11n.pt"

    # SmartLife / ONVIF CCTV Configuration (no defaults: must be provided per farm via env)
    ONVIF_HOST: str = ""
    ONVIF_PORT: int = 80
    ONVIF_USER: str = ""
    ONVIF_PASSWORD: str = ""
    RTSP_STREAM_URL: str = ""

    # Sampling & Capture Configuration
    FRAME_SAMPLING_INTERVAL_SEC: int = 5  # Capture 1 keyframe every N seconds
    MOTION_DETECTION_THRESHOLD: float = 10000.0  # Threshold for motion detection
    MAX_RTSP_RECONNECT_ATTEMPTS: int = 5

    # PostgreSQL Database Configuration
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cctv_db"
    DATABASE_URL: Optional[str] = None

    # Oracle Cloud Infrastructure (OCI) Configuration
    OCI_CONFIG_FILE: str = "~/.oci/config"
    OCI_CONFIG_DIR: Optional[str] = None
    OCI_PROFILE: str = "DEFAULT"
    OCI_REGION: str = "ap-seoul-1"
    OCI_NAMESPACE: Optional[str] = None
    OCI_COMPARTMENT_ID: Optional[str] = None
    OCI_OBJECT_STORAGE_NAMESPACE: Optional[str] = None
    OCI_BUCKET_NAME: Optional[str] = None
    OCI_BUCKET_RAW_VIDEOS: str = "cctv-raw-videos"
    OCI_BUCKET_REFINED_FRAMES: str = "cctv-AI-VISION"
    OCI_PAR_EXPIRY_DAYS: int = 7

    # Gemini AI API Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # 2-Tier Fallback Media Streaming (Tier 1: Google Drive, Tier 2: Tailscale host). Unset = tier disabled.
    TAILSCALE_HOST_URL: Optional[str] = None

    # External FMS System Notification Webhook. Unset = webhook disabled.
    FMS_WEBHOOK_URL: Optional[str] = None

    # Google Cloud Service Account, Google Drive & Google Sheets Configuration
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = None
    GOOGLE_DRIVE_FOLDER_ID: Optional[str] = None
    GOOGLE_SHEET_ID: Optional[str] = None
    GOOGLE_SHEET_RANGE: str = "Events!A:H"
    GOOGLE_INTEGRATION_ENABLED: bool = True

    # Clip & Buffer Configuration (Event Detection)
    CLIP_PRE_EVENT_SEC: float = 3.0
    CLIP_POST_EVENT_SEC: float = 3.0
    CLIP_FPS: float = 5.0
    EVENT_COOLDOWN_SEC: float = 10.0

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """Fail fast: production must not start without an API key and DB credentials."""
        if self.is_production:
            missing = []
            if not self.API_KEY:
                missing.append("API_KEY")
            if not self.DATABASE_URL and not self.POSTGRES_PASSWORD:
                missing.append("POSTGRES_PASSWORD or DATABASE_URL")
            if missing:
                raise ValueError("Missing required settings for production: " + ", ".join(missing))
        return self

    @property
    def get_database_url(self) -> str:
        """Returns configured DATABASE_URL or constructs asyncpg PostgreSQL connection string."""
        constructed = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        if self.DATABASE_URL and ("testuser" not in constructed):
            return self.DATABASE_URL
        return constructed

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
