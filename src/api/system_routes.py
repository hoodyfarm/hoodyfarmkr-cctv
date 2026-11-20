import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends

from src.domain.models.sync_payload import FarmSyncPayload
from src.services.config_sync_service import config_sync_service
from src.services.worker_manager import worker_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["System & FMS Synchronization"])


@router.post("/sync-cameras")
def sync_cameras(payload: FarmSyncPayload) -> Dict[str, Any]:
    """
    FMS에서 등록/변경된 카메라 목록을 전달받아 로컬 hoodyfarm.yaml을 갱신하고
    파이프라인 비전 워커를 Hot-Reload합니다.
    """
    try:
        result = config_sync_service.sync_from_payload(payload)
        return result
    except ValueError as e:
        logger.warning(f"카메라 동기화 검증 실패: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("카메라 동기화 처리 중 서버 내부 오류 발생")
        raise HTTPException(status_code=500, detail=f"동기화 처리 실패: {str(e)}")


@router.get("/sync-status")
def get_sync_status() -> Dict[str, Any]:
    """
    현재 적용된 농장 프로파일 및 활성 카메라 동기화 상태를 조회합니다.
    """
    profile = worker_manager.profile
    return {
        "farm_id": profile.farm_id,
        "farm_name": profile.farm_name,
        "active_camera_count": len(worker_manager.ingestion_workers),
        "cameras": [
            {
                "camera_id": cam.camera_id,
                "name": cam.name,
                "zone": cam.zone,
                "fps": cam.target_fps,
                "enabled": cam.enabled,
                "is_running": cam.camera_id in worker_manager.ingestion_workers,
            }
            for cam in profile.cameras
        ],
    }
