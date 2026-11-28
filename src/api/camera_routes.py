from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from src.config import settings
from src.services.onvif_service import ONVIFCameraService
from src.services.stream_service import VideoStreamHandler, auto_heal_camera_ip
from src.domain.models.sync_payload import FarmSyncPayload
from src.services.config_sync_service import config_sync_service
from src.services.network_scanner import AsyncNetworkScanner
from src.tools.scan_cameras import update_yaml_with_shifted_ips

# /api/v1/camera (단수형 호환) 및 /api/v1/cameras (복수형 REST 표준)
router = APIRouter(prefix="/api/v1/camera", tags=["SmartLife ONVIF CCTV"])
cameras_router = APIRouter(prefix="/api/v1/cameras", tags=["CCTV Cameras & Auto-Healing"])


class CameraConfigPayload(BaseModel):
    host: str
    port: int = 80
    user: str
    password: str


class CameraScanRequest(BaseModel):
    subnet: str = "192.168.0.0/24"
    ports: Optional[List[int]] = None
    timeout: float = 0.8
    update_yaml: bool = False


@router.get("/info")
def get_camera_info() -> Dict[str, Any]:
    """Get configured ONVIF camera device information."""
    onvif_service = ONVIFCameraService(
        host=settings.ONVIF_HOST,
        port=settings.ONVIF_PORT,
        user=settings.ONVIF_USER,
        pass_word=settings.ONVIF_PASSWORD,
    )
    return onvif_service.get_device_information()


@router.get("/profiles")
def get_camera_profiles() -> List[Dict[str, Any]]:
    """Get available ONVIF media profiles (Main stream, Sub stream)."""
    onvif_service = ONVIFCameraService(
        host=settings.ONVIF_HOST,
        port=settings.ONVIF_PORT,
        user=settings.ONVIF_USER,
        pass_word=settings.ONVIF_PASSWORD,
    )
    return onvif_service.get_profiles()


@router.post("/connect")
def connect_camera(payload: CameraConfigPayload) -> Dict[str, Any]:
    """Connect to a SmartLife ONVIF camera with provided parameters."""
    onvif_service = ONVIFCameraService(
        host=payload.host,
        port=payload.port,
        user=payload.user,
        pass_word=payload.password,
    )
    success = onvif_service.connect()
    if not success:
        raise HTTPException(status_code=400, detail="Failed to connect to ONVIF camera.")

    stream_url = onvif_service.get_stream_url()
    return {
        "status": "connected",
        "device_info": onvif_service.get_device_information(),
        "stream_url": stream_url,
    }


@router.get("/stream")
def get_live_stream():
    """MJPEG Live CCTV Video Streaming Endpoint for browser/dashboard integration."""
    stream_handler = VideoStreamHandler(settings.RTSP_STREAM_URL)
    return StreamingResponse(
        stream_handler.generate_mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/sync")
def sync_cameras_alias(payload: FarmSyncPayload) -> Dict[str, Any]:
    """POST /api/v1/system/sync-cameras의 편의용 alias 엔드포인트."""
    try:
        return config_sync_service.sync_from_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"동기화 실패: {str(e)}")


# -----------------------------------------------------------------------------
# ONVIF IP 이탈 자동 감지 & 자율 힐링 엔드포인트
# -----------------------------------------------------------------------------
async def _execute_camera_scan(req: Optional[CameraScanRequest] = None) -> Dict[str, Any]:
    payload = req or CameraScanRequest()
    ports = payload.ports or [80, 8899]
    scanner = AsyncNetworkScanner(
        subnet=payload.subnet,
        ports=ports,
        timeout=payload.timeout,
    )

    discovered = await scanner.scan_and_resolve()
    shifted = [c.to_dict() for c in discovered if c.status == "IP_SHIFTED"]

    updated_yaml_count = 0
    if payload.update_yaml:
        updated_yaml_count = update_yaml_with_shifted_ips(discovered)

    return {
        "status": "success",
        "scanned_count": len(discovered),
        "online_count": sum(1 for c in discovered if c.status in ("NORMAL", "IP_SHIFTED")),
        "shifted_count": len(shifted),
        "updated_yaml_count": updated_yaml_count,
        "cameras": [c.to_dict() for c in discovered],
        "shifted_cameras": shifted,
    }


def _execute_auto_heal(camera_id: str) -> Dict[str, Any]:
    new_ip = auto_heal_camera_ip(camera_id=camera_id)
    if new_ip:
        return {
            "status": "healed",
            "camera_id": camera_id,
            "new_ip": new_ip,
            "message": f"[{camera_id}] 카메라 IP가 {new_ip}로 자율 복구되었습니다.",
        }
    else:
        return {
            "status": "failed",
            "camera_id": camera_id,
            "new_ip": None,
            "message": f"[{camera_id}] 카메라를 탐색하지 못했거나 쿨다운 활성 중입니다.",
        }


@router.post("/scan")
async def scan_cameras_single(req: Optional[CameraScanRequest] = None) -> Dict[str, Any]:
    """서브넷 고속 스캔 및 기기 목록 / 변경 IP 반환 (단수형 경로)."""
    return await _execute_camera_scan(req)


@cameras_router.post("/scan")
async def scan_cameras_plural(req: Optional[CameraScanRequest] = None) -> Dict[str, Any]:
    """POST /api/v1/cameras/scan: 서브넷 스캔 결과(감지된 기기 목록, 변경된 IP 내역) 반환."""
    return await _execute_camera_scan(req)


@router.post("/{id}/auto-heal")
def auto_heal_camera_single(id: str) -> Dict[str, Any]:
    """특정 카메라 강제 자율 힐링 트리거 (단수형 경로)."""
    return _execute_auto_heal(id)


@cameras_router.post("/{id}/auto-heal")
def auto_heal_camera_plural(id: str) -> Dict[str, Any]:
    """POST /api/v1/cameras/{id}/auto-heal: 특정 카메라 강제 자율 힐링 트리거."""
    return _execute_auto_heal(id)
