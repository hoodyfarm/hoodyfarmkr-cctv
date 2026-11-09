import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from src.services.oci_service import OCIDataPipelineService

@pytest.mark.unit
def test_oci_upload_frame(mock_jpeg_bytes):
    service = OCIDataPipelineService()
    res = service.upload_frame_to_oci(mock_jpeg_bytes, "test_cam/frame_01.jpg", metadata={"cam": "01"})
    assert res["status"] in ["simulated", "success"]
    assert res["bucket"] == "cctv-refined-frames"
    assert res["object_name"] == "test_cam/frame_01.jpg"
    assert "oci_url" in res

@pytest.mark.unit
def test_oci_upload_file_direct():
    service = OCIDataPipelineService()
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake_mp4_bytes")
        temp_path = f.name

    try:
        res = service.upload_file_to_oci(temp_path, object_name="test_clips/clip_01.mp4")
        assert res["status"] in ["simulated", "success"]
        assert res["bucket"] == "cctv-raw-videos"
        assert res["object_name"] == "test_clips/clip_01.mp4"
        assert "oci_url" in res
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@pytest.mark.unit
def test_oci_sdk_put_object_and_par_mock():
    # Mock OCI SDK client
    mock_client = MagicMock()
    mock_put_res = MagicMock()
    mock_put_res.headers = {"etag": "mock_etag_123"}
    mock_client.put_object.return_value = mock_put_res

    mock_par_res = MagicMock()
    mock_par_res.data.access_uri = "/p/sample-par-token/n/test-ns/b/cctv-raw-videos/o/test.mp4"
    mock_client.create_preauthenticated_request.return_value = mock_par_res
    mock_client.base_client.get_endpoint.return_value = "https://objectstorage.ap-seoul-1.oraclecloud.com"

    service = OCIDataPipelineService()
    service.client = mock_client
    service.namespace = "test-ns"

    res = service.upload_video_clip_to_oci(b"video_bytes", "test.mp4")
    assert res["status"] == "success"
    assert res["etag"] == "mock_etag_123"
    assert "https://objectstorage.ap-seoul-1.oraclecloud.com/p/sample-par-token" in res["oci_url"]
    assert mock_client.put_object.called
    assert mock_client.create_preauthenticated_request.called

@pytest.mark.unit
def test_oci_record_metadata():
    service = OCIDataPipelineService()
    success = service.record_metadata_to_oci_db({"frame_id": "01", "status": "ok"})
    assert success is True
