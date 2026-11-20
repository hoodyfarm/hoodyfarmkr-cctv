import os
import shutil
import logging
from typing import Dict, Any, Optional
import yaml

from src.config import settings
from src.domain.models.farm_profile import FarmProfile
from src.domain.models.sync_payload import FarmSyncPayload
from src.services.worker_manager import worker_manager

logger = logging.getLogger(__name__)


class ConfigSyncService:
    """
    FMS(SmartLife 연동)로부터 수신한 카메라 설정 정보를 바탕으로
    로컬 hoodyfarm.yaml을 업데이트하고 비전 워커를 Hot-Reload하는 서비스.
    """

    def __init__(self, yaml_path: Optional[str] = None):
        self.yaml_path = yaml_path or settings.FARM_PROFILE_PATH or "config/farms/hoodyfarm.yaml"

    def sync_from_payload(self, payload: FarmSyncPayload) -> Dict[str, Any]:
        """
        1. 페이로드 유효성 검사
        2. 기존 YAML 백업 (.bak)
        3. 새 카메라 설정으로 YAML 파일 갱신 (기존 rules/storage/notification 보존)
        4. FarmProfile 로드 및 WorkerManager Hot-Reload 트리거
        """
        if not payload.cameras:
            raise ValueError("카메라 목록이 비어 있습니다. 최소 1대 이상의 카메라가 필요합니다.")

        # 중복 camera_id 검증
        cam_ids = [c.camera_id for c in payload.cameras]
        if len(cam_ids) != len(set(cam_ids)):
            raise ValueError(f"중복된 camera_id가 존재합니다: {cam_ids}")

        # 1. 기존 설정 파일 읽기
        existing_data: Dict[str, Any] = {}
        if os.path.exists(self.yaml_path):
            try:
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    existing_data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"기존 YAML 로드 중 오류 (기본값으로 대체): {e}")

        # 2. 백업 파일 생성
        backup_path = f"{self.yaml_path}.bak"
        try:
            if os.path.exists(self.yaml_path):
                shutil.copy2(self.yaml_path, backup_path)
                logger.info(f"기존 설정을 {backup_path}에 백업했습니다.")
        except Exception as e:
            logger.warning(f"YAML 백업 파일 생성 실패 (진행은 계속됨): {e}")

        # 3. 새로운 YAML 데이터 구조 조립
        updated_cameras = []
        for cam in payload.cameras:
            raw_url = cam.build_rtsp_url()
            # 환경변수 치환 템플릿 지원 (예: ${RTSP_STREAM_URL:-...})
            if cam.camera_id in ("CAM_BARN_01", "cam_01"):
                rtsp_env_var = "RTSP_STREAM_URL"
            elif cam.camera_id in ("CAM_BARN_02", "cam_02"):
                rtsp_env_var = "RTSP_STREAM_URL_CAM02"
            else:
                rtsp_env_var = f"RTSP_STREAM_URL_{cam.camera_id}"
            
            templated_url = f"${{{rtsp_env_var}:-{raw_url}}}" if not str(raw_url).startswith("${") else raw_url

            cam_entry = {
                "camera_id": cam.camera_id,
                "name": cam.camera_name,
                "zone": cam.zone or "pen_01",
                "rtsp_url": templated_url,
                "target_fps": float(cam.fps),
                "ring_buffer_sec": float(cam.ring_buffer_sec),
                "enabled": bool(cam.enabled),
            }
            updated_cameras.append(cam_entry)

        # farm_id가 환경변수 템플릿 형태(${FARM_ID:-...})인 경우 보존
        existing_farm_id = existing_data.get("farm_id", "${FARM_ID:-hoodyfarm}")
        if payload.farm_id and payload.farm_id not in ("hoodyfarm", "default"):
            farm_id_val = payload.farm_id
        elif str(existing_farm_id).startswith("${"):
            farm_id_val = existing_farm_id
        else:
            farm_id_val = f"${{FARM_ID:-{payload.farm_id or 'hoodyfarm'}}}"

        updated_data: Dict[str, Any] = {
            "farm_id": farm_id_val,
            "farm_name": payload.farm_name or existing_data.get("farm_name", "후디팜 한우 스마트축사"),
            "cameras": updated_cameras,
            "rules": existing_data.get("rules", {
                "species": "cattle",
                "target_classes": ["cow", "person", "dog"],
                "confidence_threshold": 0.25,
                "cooldown_sec": 10.0,
                "pre_event_sec": 3.0,
                "post_event_sec": 3.0,
            }),
            "storage": existing_data.get("storage", {
                "media_priority": ["drive", "tailscale", "oci"],
                "spool_retention_minutes": 15,
                "event_retention_days": 7,
                "max_total_mb": 2048,
            }),
            "notification": existing_data.get("notification", {
                "fms_webhook_url": settings.FMS_WEBHOOK_URL or "",
                "tailscale_host_url": settings.TAILSCALE_HOST_URL or "",
                "timeout_sec": 4.0,
            }),
        }

        # 4. YAML 파일 저장
        os.makedirs(os.path.dirname(os.path.abspath(self.yaml_path)), exist_ok=True)
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                updated_data,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        logger.info(f"설정 파일({self.yaml_path}) 갱신 완료.")

        # 5. FarmProfile 로드 및 WorkerManager Hot-Reload
        new_profile = FarmProfile.from_yaml(self.yaml_path)
        reload_result = worker_manager.reload_from_profile(new_profile)

        return {
            "status": "success",
            "farm_id": new_profile.farm_id,
            "synced_cameras": len(updated_cameras),
            "camera_ids": [c["camera_id"] for c in updated_cameras],
            "backup_file": backup_path if os.path.exists(backup_path) else None,
            "workers": reload_result,
        }


config_sync_service = ConfigSyncService()
