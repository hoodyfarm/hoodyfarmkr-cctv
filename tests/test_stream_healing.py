import os
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import yaml

from src.main import app
from src.config import settings
from src.services.stream_service import (
    VideoStreamHandler,
    auto_heal_camera_ip,
    reset_auto_heal_state,
    INITIAL_COOLDOWN_SEC,
    MAX_COOLDOWN_SEC,
)
from src.services.network_scanner import DiscoveredCamera


@pytest.fixture(autouse=True)
def clean_cooldowns():
    reset_auto_heal_state()
    yield
    reset_auto_heal_state()


def test_video_stream_handler_auto_heal_trigger_on_3_failures(tmp_path):
    test_yaml = tmp_path / "hoodyfarm.yaml"
    initial_yaml = """
farm_id: hoodyfarm
cameras:
- camera_id: CAM_BARN_02
  rtsp_url: ${RTSP_STREAM_URL_CAM02:-rtsp://192.168.0.12/live/0/SUB}
"""
    test_yaml.write_text(initial_yaml, encoding="utf-8")

    handler = VideoStreamHandler(
        stream_url="rtsp://192.168.0.12/live/0/SUB",
        camera_id="CAM_BARN_02",
        yaml_path=str(test_yaml),
    )

    # cv2.VideoCapture 실패 시뮬레이션
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False

    with patch("cv2.VideoCapture", return_value=mock_cap), \
         patch("src.services.stream_service.auto_heal_camera_ip") as mock_heal:
        mock_heal.return_value = "192.168.0.105"

        # 1회 실패
        frame1 = handler.capture_single_frame()
        assert frame1 is None
        assert handler.consecutive_failures == 1
        mock_heal.assert_not_called()

        # 2회 실패
        frame2 = handler.capture_single_frame()
        assert frame2 is None
        assert handler.consecutive_failures == 2
        mock_heal.assert_not_called()

        # 3회 실패 -> auto_heal_camera_ip 격발!
        frame3 = handler.capture_single_frame()
        assert frame3 is None
        mock_heal.assert_called_once_with("CAM_BARN_02", yaml_path=str(test_yaml))
        assert "192.168.0.105" in handler.stream_url
        assert handler.consecutive_failures == 0  # 핫리로드 후 리셋


def test_auto_heal_camera_ip_updates_yaml_and_cooldown(tmp_path):
    test_yaml = tmp_path / "hoodyfarm.yaml"
    test_yaml.write_text(
        """
farm_id: hoodyfarm
cameras:
- camera_id: CAM_BARN_02
  rtsp_url: rtsp://192.168.0.12/live/0/SUB
""",
        encoding="utf-8",
    )

    mock_arp = {"192.168.0.105": "5A-5A-00-A0-91-FD"}  # CAM_BARN_02

    # 1. 정상 새 IP 발견 시 자율 힐링 및 YAML 갱신
    new_ip = auto_heal_camera_ip(
        camera_id="CAM_BARN_02",
        yaml_path=str(test_yaml),
        arp_cache_override=mock_arp,
    )
    assert new_ip == "192.168.0.105"

    updated_yaml = test_yaml.read_text(encoding="utf-8")
    assert "192.168.0.105" in updated_yaml
    assert (tmp_path / "hoodyfarm.yaml.bak").exists()


def test_exponential_backoff_cooldown(tmp_path):
    # 장비가 완전히 꺼져 있는 경우 (ARP/스캔 모두 미검출)
    mock_arp = {}

    with patch("src.services.network_scanner.AsyncNetworkScanner.scan_and_resolve") as mock_scan:
        mock_scan.return_value = []

        # 1차 실패: 10초 쿨다운 진입
        res1 = auto_heal_camera_ip(
            camera_id="CAM_BARN_03",
            yaml_path=str(tmp_path / "none.yaml"),
            arp_cache_override=mock_arp,
        )
        assert res1 is None

        # 쿨다운 진행 중 즉시 재호출 -> 스캔 건너뛰고 바로 None 반환
        res_skipped = auto_heal_camera_ip(
            camera_id="CAM_BARN_03",
            yaml_path=str(tmp_path / "none.yaml"),
            arp_cache_override=mock_arp,
        )
        assert res_skipped is None


def test_fastapi_camera_scan_and_auto_heal_endpoints():
    client = TestClient(app)
    headers = {"X-API-Key": settings.API_KEY} if settings.API_KEY else {}

    # 1. POST /api/v1/cameras/scan 테스트
    sample_discovered = [
        DiscoveredCamera(
            camera_id="CAM_BARN_02",
            name="cctv2",
            mac="5A-5A-00-A0-91-FD",
            current_ip="192.168.0.105",
            default_ip="192.168.0.12",
            port=80,
            is_matched=True,
            is_ip_changed=True,
            status="IP_SHIFTED",
            rtsp_url="rtsp://192.168.0.105/live/0/SUB",
        )
    ]

    with patch("src.services.network_scanner.AsyncNetworkScanner.scan_and_resolve") as mock_scan:
        mock_scan.return_value = sample_discovered

        resp = client.post("/api/v1/cameras/scan", json={"subnet": "192.168.0.0/24"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["shifted_count"] == 1
        assert len(data["shifted_cameras"]) == 1
        assert data["shifted_cameras"][0]["camera_id"] == "CAM_BARN_02"
        assert data["shifted_cameras"][0]["current_ip"] == "192.168.0.105"

    # 2. POST /api/v1/cameras/{id}/auto-heal 테스트 (성공)
    with patch("src.api.camera_routes.auto_heal_camera_ip", return_value="192.168.0.105"):
        resp_heal = client.post("/api/v1/cameras/CAM_BARN_02/auto-heal", headers=headers)
        assert resp_heal.status_code == 200
        heal_data = resp_heal.json()
        assert heal_data["status"] == "healed"
        assert heal_data["new_ip"] == "192.168.0.105"

    # 3. POST /api/v1/cameras/{id}/auto-heal 테스트 (실패/쿨다운)
    with patch("src.api.camera_routes.auto_heal_camera_ip", return_value=None):
        resp_fail = client.post("/api/v1/cameras/CAM_BARN_99/auto-heal", headers=headers)
        assert resp_fail.status_code == 200
        fail_data = resp_fail.json()
        assert fail_data["status"] == "failed"
        assert fail_data["new_ip"] is None
