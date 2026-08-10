from src.services.oci_service import OCIDataPipelineService

def test_oci_service_simulated_frame_upload():
    service = OCIDataPipelineService()
    dummy_bytes = b"test_frame_bytes"
    res = service.upload_frame_to_oci(dummy_bytes, "cam_test/frame1.jpg")
    assert res["status"] in ["simulated", "success"]
    assert res["object_name"] == "cam_test/frame1.jpg"

def test_oci_service_simulated_video_upload():
    service = OCIDataPipelineService()
    dummy_video_bytes = b"test_video_mp4_bytes"
    res = service.upload_video_clip_to_oci(dummy_video_bytes, "cam_test/clip1.mp4")
    assert res["status"] in ["simulated", "success"]
    assert res["bucket"] == "cctv-raw-videos"
