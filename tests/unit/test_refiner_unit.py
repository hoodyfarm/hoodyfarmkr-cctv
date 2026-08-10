import pytest
from src.services.refiner import VideoDataRefiner

@pytest.mark.unit
def test_refine_frame_resizing_and_metadata(mock_bgr_frame):
    refiner = VideoDataRefiner(target_width=640, target_height=360)
    frame_bytes, metadata = refiner.refine_frame(mock_bgr_frame)

    assert isinstance(frame_bytes, bytes)
    assert len(frame_bytes) > 0
    assert metadata["width"] == 640
    assert metadata["height"] == 360
    assert metadata["format"] == "jpeg"
    assert "timestamp" in metadata

@pytest.mark.unit
def test_motion_detection(mock_bgr_frame):
    refiner = VideoDataRefiner()
    # Identical frames should return False (no motion)
    has_motion = refiner.detect_motion(mock_bgr_frame, mock_bgr_frame, threshold=1000.0)
    assert has_motion is False
