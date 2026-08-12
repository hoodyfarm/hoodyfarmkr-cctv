import pytest
import numpy as np
from src.services.stream_service import VideoStreamHandler

@pytest.mark.unit
def test_synthetic_frame_generation():
    handler = VideoStreamHandler(stream_url="rtsp://localhost/test")
    frame = handler.generate_synthetic_test_frame("Unit Test Synthetic Frame")
    
    assert frame is not None
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (480, 640, 3)

@pytest.mark.unit
def test_frame_to_jpeg_bytes():
    handler = VideoStreamHandler(stream_url="rtsp://localhost/test")
    frame = handler.generate_synthetic_test_frame("JPEG Test Frame")
    jpeg_bytes = handler.frame_to_jpeg_bytes(frame)
    
    assert jpeg_bytes is not None
    assert isinstance(jpeg_bytes, bytes)
    assert len(jpeg_bytes) > 0
    # Check JPEG magic header 0xFF 0xD8
    assert jpeg_bytes[:2] == b'\xff\xd8'

@pytest.mark.unit
def test_motion_delta_calculation():
    handler = VideoStreamHandler(stream_url="rtsp://localhost/test")
    frame1 = handler.generate_synthetic_test_frame("Frame 1")
    
    # Identical frames should yield 0 motion delta
    delta_same = handler.calculate_motion_delta(frame1, frame1)
    assert delta_same == 0.0

    # Frame with drawn box should yield positive delta
    frame2 = frame1.copy()
    frame2[100:200, 100:200] = (255, 255, 255)
    delta_diff = handler.calculate_motion_delta(frame1, frame2)
    assert delta_diff > 0.0

@pytest.mark.unit
def test_capture_frame_with_retry_fallback():
    # Invalid RTSP URL should gracefully fallback to synthetic frame
    handler = VideoStreamHandler(stream_url="rtsp://invalid-non-existent-ip:554/stream")
    frame, is_synthetic = handler.capture_frame_with_retry(max_retries=1, delay_sec=0.1)
    
    assert frame is not None
    assert is_synthetic is True
    assert frame.shape == (480, 640, 3)
