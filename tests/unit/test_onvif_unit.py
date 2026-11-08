import pytest
from src.services.onvif_service import ONVIFCameraService

from unittest.mock import patch, MagicMock

@pytest.mark.unit
@patch("src.services.onvif_service.ONVIFCamera")
def test_onvif_connect_and_stream_uri_generation(mock_camera_cls, mock_onvif_credentials):
    mock_cam = MagicMock()
    mock_media = MagicMock()
    mock_profile = MagicMock()
    mock_profile.token = "profile_01"
    mock_media.GetProfiles.return_value = [mock_profile]
    mock_stream_uri = MagicMock()
    mock_stream_uri.Uri = "rtsp://192.168.1.100:554/stream1"
    mock_media.GetStreamUri.return_value = mock_stream_uri
    mock_cam.create_media_service.return_value = mock_media
    mock_camera_cls.return_value = mock_cam

    service = ONVIFCameraService(
        host=mock_onvif_credentials["host"],
        port=mock_onvif_credentials["port"],
        user=mock_onvif_credentials["user"],
        pass_word=mock_onvif_credentials["password"]
    )
    assert service.connect() is True
    url = service.get_stream_url()
    assert "192.168.1.100:554/stream1" in url

@pytest.mark.unit
@patch("src.services.onvif_service.ONVIFCamera")
def test_onvif_profiles_fallback(mock_camera_cls, mock_onvif_credentials):
    mock_camera_cls.side_effect = Exception("Connection timed out")
    service = ONVIFCameraService(
        host=mock_onvif_credentials["host"],
        port=mock_onvif_credentials["port"],
        user=mock_onvif_credentials["user"],
        pass_word=mock_onvif_credentials["password"]
    )
    profiles = service.get_profiles()
    assert len(profiles) >= 1
    assert "token" in profiles[0]
