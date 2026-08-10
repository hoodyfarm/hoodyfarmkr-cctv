import pytest
from src.services.oci_service import OCIDataPipelineService

@pytest.mark.unit
def test_oci_upload_frame(mock_jpeg_bytes):
    service = OCIDataPipelineService()
    res = service.upload_frame_to_oci(mock_jpeg_bytes, "test_cam/frame_01.jpg", metadata={"cam": "01"})
    assert res["status"] in ["simulated", "success"]
    assert res["bucket"] == "cctv-refined-frames"
    assert res["object_name"] == "test_cam/frame_01.jpg"

@pytest.mark.unit
def test_oci_record_metadata():
    service = OCIDataPipelineService()
    success = service.record_metadata_to_oci_db({"frame_id": "01", "status": "ok"})
    assert success is True
