import os
import tempfile
import yaml
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.domain.models.sync_payload import CameraSyncItem, FarmSyncPayload
from src.services.config_sync_service import ConfigSyncService, config_sync_service
from src.services.worker_manager import worker_manager


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.mark.unit
def test_camera_sync_item_rtsp_url_builder():
    # 1. 명시적 rtsp_url이 있는 경우
    c1 = CameraSyncItem(
        camera_id="cam_01",
        camera_name="Camera 1",
        local_ip="192.168.0.100",
        username="admin",
        password="secret!",
        rtsp_url="rtsp://custom:123/live",
    )
    assert c1.build_rtsp_url() == "rtsp://custom:123/live"

    # 2. rtsp_url이 비어있는 경우 자동 조합
    c2 = CameraSyncItem(
        camera_id="cam_02",
        camera_name="Camera 2",
        local_ip="192.168.0.101",
        username="admin",
        password="secret!",
    )
    assert c2.build_rtsp_url() == "rtsp://admin:secret!@192.168.0.101:554/streamtype=1"


@pytest.mark.unit
def test_config_sync_service_validation():
    sync_svc = ConfigSyncService(yaml_path="dummy.yaml")

    # 빈 카메라 목록 거부
    with pytest.raises(ValueError, match="최소 1대 이상"):
        sync_svc.sync_from_payload(FarmSyncPayload(farm_id="hoodyfarm", cameras=[]))

    # 중복 ID 거부
    dup_payload = FarmSyncPayload(
        farm_id="hoodyfarm",
        cameras=[
            CameraSyncItem(camera_id="cam_dup", camera_name="Cam 1", local_ip="192.168.0.1"),
            CameraSyncItem(camera_id="cam_dup", camera_name="Cam 2", local_ip="192.168.0.2"),
        ],
    )
    with pytest.raises(ValueError, match="중복된 camera_id"):
        sync_svc.sync_from_payload(dup_payload)


@pytest.mark.unit
def test_config_sync_service_executes_backup_and_yaml_update(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_yaml = os.path.join(tmpdir, "hoodyfarm_test.yaml")
        init_data = {
            "farm_id": "test_farm",
            "farm_name": "Test Farm Initial",
            "cameras": [
                {
                    "camera_id": "CAM_OLD",
                    "name": "Old Camera",
                    "rtsp_url": "rtsp://old:554/live",
                    "target_fps": 5.0,
                    "ring_buffer_sec": 10.0,
                    "enabled": True,
                }
            ],
            "rules": {"species": "cattle", "confidence_threshold": 0.3},
        }
        with open(tmp_yaml, "w", encoding="utf-8") as f:
            yaml.safe_dump(init_data, f)

        sync_svc = ConfigSyncService(yaml_path=tmp_yaml)

        # WorkerManager reload를 mock
        reloaded = []
        monkeypatch.setattr(worker_manager, "reload_from_profile", lambda p: reloaded.append(p) or {"status": "mock_reloaded"})

        payload = FarmSyncPayload(
            farm_id="hoodyfarm_synced",
            farm_name="동기화된 후디팜",
            cameras=[
                CameraSyncItem(
                    camera_id="CAM_NEW_01",
                    camera_name="1번 축사 (송아지방)",
                    local_ip="192.168.0.217",
                    username="admin",
                    password="pass1",
                ),
                CameraSyncItem(
                    camera_id="CAM_NEW_02",
                    camera_name="2번 축사 (비육우)",
                    local_ip="192.168.0.25",
                    username="admin",
                    password="pass2",
                ),
            ],
        )

        result = sync_svc.sync_from_payload(payload)
        assert result["status"] == "success"
        assert result["synced_cameras"] == 2
        assert result["camera_ids"] == ["CAM_NEW_01", "CAM_NEW_02"]

        # 1. 백업 파일 검증
        bak_file = f"{tmp_yaml}.bak"
        assert os.path.exists(bak_file)
        with open(bak_file, "r", encoding="utf-8") as f:
            bak_data = yaml.safe_load(f)
            assert bak_data["farm_id"] == "test_farm"

        # 2. 갱신된 YAML 파일 검증
        with open(tmp_yaml, "r", encoding="utf-8") as f:
            new_data = yaml.safe_load(f)
            assert new_data["farm_id"] == "hoodyfarm_synced"
            assert len(new_data["cameras"]) == 2
            assert new_data["cameras"][0]["name"] == "1번 축사 (송아지방)"
            assert new_data["rules"]["species"] == "cattle"

        # 3. reload_from_profile 호출 확인
        assert len(reloaded) == 1
        assert reloaded[0].farm_id == "hoodyfarm_synced"


@pytest.mark.unit
def test_sync_api_endpoints(test_client, monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_yaml = os.path.join(tmpdir, "hoodyfarm_api_test.yaml")
        monkeypatch.setattr(config_sync_service, "yaml_path", tmp_yaml)
        monkeypatch.setattr(worker_manager, "reload_from_profile", lambda p: {"status": "reloaded"})

        payload = {
            "farm_id": "hoodyfarm",
            "farm_name": "후디팜 테스트",
            "cameras": [
                {
                    "camera_id": "CAM_SYNC_01",
                    "camera_name": "동기화 카메라",
                    "local_ip": "192.168.0.217",
                    "onvif_port": 8899,
                    "username": "admin",
                    "password": "pwd",
                    "fps": 5.0,
                    "enabled": True,
                }
            ],
        }

        # 1. POST /api/v1/system/sync-cameras
        res = test_client.post("/api/v1/system/sync-cameras", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert res.json()["synced_cameras"] == 1

        # 2. POST /api/v1/camera/sync (alias)
        res_alias = test_client.post("/api/v1/camera/sync", json=payload)
        assert res_alias.status_code == 200
        assert res_alias.json()["status"] == "success"

        # 3. GET /api/v1/system/sync-status
        res_status = test_client.get("/api/v1/system/sync-status")
        assert res_status.status_code == 200
        assert "active_camera_count" in res_status.json()
