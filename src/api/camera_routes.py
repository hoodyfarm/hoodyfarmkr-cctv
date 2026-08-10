from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List

from src.config import settings
from src.services.onvif_service import ONVIFCameraService
from src.services.stream_service import VideoStreamHandler

router = APIRouter(prefix="/api/v1/camera", tags=["SmartLife ONVIF CCTV"])

class CameraConfigPayload(BaseModel):
    host: str
    port: int = 80
    user: str
    password: str

@router.get("/info")
def get_camera_info() -> Dict[str, Any]:
    """
    Get configured ONVIF camera device information.
    """
    onvif_service = ONVIFCameraService(
        host=settings.ONVIF_HOST,
        port=settings.ONVIF_PORT,
        user=settings.ONVIF_USER,
        pass_word=settings.ONVIF_PASSWORD
    )
    return onvif_service.get_device_information()

@router.get("/profiles")
def get_camera_profiles() -> List[Dict[str, Any]]:
    """
    Get available ONVIF media profiles (Main stream, Sub stream).
    """
    onvif_service = ONVIFCameraService(
        host=settings.ONVIF_HOST,
        port=settings.ONVIF_PORT,
        user=settings.ONVIF_USER,
        pass_word=settings.ONVIF_PASSWORD
    )
    return onvif_service.get_profiles()

@router.post("/connect")
def connect_camera(payload: CameraConfigPayload) -> Dict[str, Any]:
    """
    Connect to a SmartLife ONVIF camera with provided parameters.
    """
    onvif_service = ONVIFCameraService(
        host=payload.host,
        port=payload.port,
        user=payload.user,
        pass_word=payload.password
    )
    success = onvif_service.connect()
    if not success:
        raise HTTPException(status_code=400, detail="Failed to connect to ONVIF camera.")
    
    stream_url = onvif_service.get_stream_url()
    return {
        "status": "connected",
        "device_info": onvif_service.get_device_information(),
        "stream_url": stream_url
    }

@router.get("/stream")
def get_live_stream():
    """
    MJPEG Live CCTV Video Streaming Endpoint for browser/dashboard integration.
    """
    stream_handler = VideoStreamHandler(settings.RTSP_STREAM_URL)
    return StreamingResponse(
        stream_handler.generate_mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
