import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App General Settings
    APP_NAME: str = "hoodyfarmkr-cctv"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # SmartLife / ONVIF CCTV Configuration
    ONVIF_HOST: str = "192.168.1.100"
    ONVIF_PORT: int = 80
    ONVIF_USER: str = "admin"
    ONVIF_PASSWORD: str = "your_cctv_password"
    RTSP_STREAM_URL: str = "rtsp://admin:your_cctv_password@192.168.1.100:554/stream1"
    
    # Sampling & Capture Configuration
    FRAME_SAMPLING_INTERVAL_SEC: int = 5  # Capture 1 keyframe every N seconds
    MOTION_DETECTION_THRESHOLD: float = 10000.0  # Threshold for motion detection
    MAX_RTSP_RECONNECT_ATTEMPTS: int = 5

    # PostgreSQL Database Configuration (Stage 3 & Docker Deployment)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_cctv_pass"
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

    # Gemini AI API Configuration (Stage 4)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # 2-Tier Fallback Media Streaming Configuration (Tailscale 3500X & Google Drive)
    TAILSCALE_HOST_URL: str = "http://100.75.197.92:8000"

    # External FMS System Notification Webhook (hoodyfarmkr-fms integration)
    FMS_WEBHOOK_URL: Optional[str] = "http://localhost:3000/api/v1/cctv-events"

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
