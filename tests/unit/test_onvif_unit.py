import pytest
from src.services.onvif_service import ONVIFCameraService

@pytest.mark.unit
def test_onvif_connect_and_stream_uri_generation(mock_onvif_credentials):
    service = ONVIFCameraService(
        host=mock_onvif_credentials["host"],
        port=mock_onvif_credentials["port"],
        user=mock_onvif_credentials["user"],
        pass_word=mock_onvif_credentials["password"]
    )
    assert service.connect() is True
    url = service.get_stream_url()
    assert "rtsp://admin:test_password@192.168.1.100:554/stream1" in url

@pytest.mark.unit
def test_onvif_profiles_fallback(mock_onvif_credentials):
    service = ONVIFCameraService(
        host=mock_onvif_credentials["host"],
        port=mock_onvif_credentials["port"],
        user=mock_onvif_credentials["user"],
        pass_word=mock_onvif_credentials["password"]
    )
    profiles = service.get_profiles()
    assert len(profiles) >= 1
    assert "token" in profiles[0]
