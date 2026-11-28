import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.services.network_scanner import (
    HARDWARE_MASTER_REGISTRY,
    normalize_mac,
    get_arp_table,
    OnvifDeviceResolver,
    AsyncNetworkScanner,
    DiscoveredCamera,
)
from src.tools.scan_cameras import format_table, update_yaml_with_shifted_ips


def test_normalize_mac():
    assert normalize_mac("5a:5a:00:a0:91:fd") == "5A-5A-00-A0-91-FD"
    assert normalize_mac("5A-5A-00-A0-91-FD") == "5A-5A-00-A0-91-FD"
    assert normalize_mac("5a5a00a091fd") == "5A-5A-00-A0-91-FD"
    assert normalize_mac("") == ""
    assert normalize_mac(None) == ""


def test_get_arp_table_parsing():
    sample_windows_arp = """
인터페이스: 192.168.0.11 --- 0x8
  인터넷 주소           물리적 주소           종류
  192.168.0.1           00-11-22-33-44-55     동적
  192.168.0.12          5a-5a-00-a0-91-fd     동적
  192.168.0.105         5a-5a-00-a0-93-19     동적
  192.168.0.201         4c-2f-7b-ee-9d-fd     동적
    """
    arp_map = get_arp_table(custom_output=sample_windows_arp)
    assert arp_map["192.168.0.12"] == "5A-5A-00-A0-91-FD"
    assert arp_map["192.168.0.105"] == "5A-5A-00-A0-93-19"
    assert arp_map["192.168.0.201"] == "4C-2F-7B-EE-9D-FD"


def test_onvif_device_resolver_mock(monkeypatch):
    xml_response = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        '<s:Body><tds:GetDeviceInformationResponse>'
        '<tds:Manufacturer>MODI-I</tds:Manufacturer>'
        '<tds:Model>IPC-MODI-2K</tds:Model>'
        '<tds:FirmwareVersion>V2.1</tds:FirmwareVersion>'
        '<tds:SerialNumber>MODI20261126</tds:SerialNumber>'
        '</tds:GetDeviceInformationResponse></s:Body></s:Envelope>'
    )

    class MockResp:
        status = 200
        def read(self):
            return xml_response.encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: MockResp())

    success, info = OnvifDeviceResolver.probe_device("192.168.0.12", 80)
    assert success is True
    assert info.get("manufacturer") == "MODI-I"
    assert info.get("model") == "IPC-MODI-2K"


@pytest.mark.asyncio
async def test_async_network_scanner_ip_shift_detection():
    # 2번 카메라(CAM_BARN_02)가 192.168.0.12에서 192.168.0.105로 밀린 상황 시뮬레이션
    scanner = AsyncNetworkScanner(subnet="192.168.0.0/24", ports=[80, 8899])

    # 1. 포트 스캔 모킹: 105(포트 80), 201(포트 8899) 열림
    async def mock_scan_open_ports():
        return [("192.168.0.105", 80), ("192.168.0.201", 8899)]

    scanner.scan_open_ports = mock_scan_open_ports

    # 2. ARP 테이블 캐시 모킹
    mock_arp = {
        "192.168.0.105": "5A-5A-00-A0-91-FD",  # CAM_BARN_02 (원래 192.168.0.12)
        "192.168.0.201": "4C-2F-7B-EE-9D-FD",  # CAM_BARN_01 (원래 192.168.0.201)
    }

    discovered = await scanner.scan_and_resolve(arp_cache_override=mock_arp)

    # CAM_BARN_02 확인
    cam02 = next((c for c in discovered if c.camera_id == "CAM_BARN_02"), None)
    assert cam02 is not None
    assert cam02.current_ip == "192.168.0.105"
    assert cam02.default_ip == "192.168.0.12"
    assert cam02.is_ip_changed is True
    assert cam02.status == "IP_SHIFTED"
    assert "192.168.0.105" in cam02.rtsp_url

    # CAM_BARN_01 확인 (정상 유지)
    cam01 = next((c for c in discovered if c.camera_id == "CAM_BARN_01"), None)
    assert cam01 is not None
    assert cam01.current_ip == "192.168.0.201"
    assert cam01.is_ip_changed is False
    assert cam01.status == "NORMAL"

    # 미감지된 CAM_BARN_03 확인 (오프라인)
    cam03 = next((c for c in discovered if c.camera_id == "CAM_BARN_03"), None)
    assert cam03 is not None
    assert cam03.status == "OFFLINE"


def test_resolve_camera_ip():
    scanner = AsyncNetworkScanner()
    mock_arp = {
        "192.168.0.105": "5A-5A-00-A0-91-FD",
        "192.168.0.201": "4C-2F-7B-EE-9D-FD",
    }
    # ID로 조회
    ip_by_id = scanner.resolve_camera_ip("CAM_BARN_02", arp_cache_override=mock_arp)
    assert ip_by_id == "192.168.0.105"

    # MAC으로 조회
    ip_by_mac = scanner.resolve_camera_ip("5a:5a:00:a0:91:fd", arp_cache_override=mock_arp)
    assert ip_by_mac == "192.168.0.105"

    # 존재하지 않는 ID
    assert scanner.resolve_camera_ip("CAM_UNKNOWN", arp_cache_override=mock_arp) is None


def test_format_table_and_update_yaml(tmp_path):
    cameras = [
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

    # 표 포맷팅 테스트
    table_str = format_table(cameras)
    assert "CAM_BARN_02" in table_str
    assert "192.168.0.105" in table_str
    assert "IP_SHIFTED" in table_str

    # YAML 갱신 테스트
    test_yaml = tmp_path / "hoodyfarm.yaml"
    initial_content = """
farm_id: hoodyfarm
cameras:
- camera_id: CAM_BARN_02
  name: 2번사 (비육우)
  rtsp_url: ${RTSP_STREAM_URL_CAM02:-rtsp://192.168.0.12/live/0/SUB}
"""
    test_yaml.write_text(initial_content, encoding="utf-8")

    updated = update_yaml_with_shifted_ips(cameras, yaml_path=str(test_yaml))
    assert updated == 1

    content_after = test_yaml.read_text(encoding="utf-8")
    assert "192.168.0.105" in content_after
    assert (tmp_path / "hoodyfarm.yaml.bak").exists()
