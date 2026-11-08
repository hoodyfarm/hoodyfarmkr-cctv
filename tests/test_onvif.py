from unittest.mock import patch, MagicMock
from src.services.onvif_service import ONVIFCameraService

def test_onvif_service_initialization():
    service = ONVIFCameraService("192.168.1.100", 80, "admin", "password")
    info = service.get_device_information()
    assert info["host"] == "192.168.1.100"
    with patch.object(service, "connect", return_value=False):
        stream_url = service.get_stream_url()
        assert "rtsp://" in stream_url

def test_onvif_service_profiles():
    service = ONVIFCameraService("192.168.1.100", 80, "admin", "password")
    with patch.object(service, "connect", return_value=False):
        profiles = service.get_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) > 0
        assert "token" in profiles[0]
