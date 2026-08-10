import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "hoodyfarmkr-cctv"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # SmartLife / ONVIF CCTV Configuration
    ONVIF_HOST: str = "192.168.1.100"
    ONVIF_PORT: int = 80
    ONVIF_USER: str = "admin"
    ONVIF_PASSWORD: str = "admin_password"
    RTSP_STREAM_URL: str = "rtsp://admin:admin_password@192.168.1.100:554/stream1"
    
    # Sampling & Capture Configuration
    FRAME_SAMPLING_INTERVAL_SEC: int = 5  # Capture 1 keyframe every 5 seconds
    MOTION_DETECTION_THRESHOLD: float = 10000.0  # Threshold for motion detection
    MAX_RTSP_RECONNECT_ATTEMPTS: int = 5

    # Oracle Cloud Infrastructure (OCI) Configuration
    OCI_CONFIG_FILE: str = "~/.oci/config"
    OCI_PROFILE: str = "DEFAULT"
    OCI_REGION: str = "ap-seoul-1"
    OCI_COMPARTMENT_ID: Optional[str] = None
    OCI_OBJECT_STORAGE_NAMESPACE: Optional[str] = None
    OCI_BUCKET_RAW_VIDEOS: str = "cctv-raw-videos"
    OCI_BUCKET_REFINED_FRAMES: str = "cctv-refined-frames"

    # Gemini AI API Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # External FMS System Notification Webhook (hoodyfarmkr-fms integration)
    FMS_WEBHOOK_URL: Optional[str] = "http://localhost:3000/api/v1/cctv-events"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
