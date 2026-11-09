import pytest
import time
import numpy as np
from unittest.mock import MagicMock, patch
from src.services.ingestion_worker import IngestionWorker

def test_ingestion_worker_initialization():
    worker = IngestionWorker("rtsp://test_url", target_fps=2.0)
    assert worker.stream_url == "rtsp://test_url"
    assert worker.target_fps == 2.0
    assert worker.interval == 0.5
    assert worker.frame_queue.maxsize == 1
    assert worker._running is False

@patch("src.services.ingestion_worker.cv2.VideoCapture")
def test_ingestion_worker_queue_zero_latency(mock_vcap):
    mock_instance = MagicMock()
    mock_instance.isOpened.return_value = True
    # Return fake frame
    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_instance.read.return_value = (True, fake_frame)
    mock_vcap.return_value = mock_instance

    worker = IngestionWorker("rtsp://dummy", target_fps=10.0, max_queue_size=1)
    worker.start()
    time.sleep(0.3)
    
    assert worker.is_connected is True
    assert worker.total_captured > 0
    
    frame = worker.get_latest_frame(timeout=0.2)
    assert frame is not None
    assert frame.shape == (100, 100, 3)
    
    worker.stop()
    assert worker._running is False

def test_ingestion_worker_ring_buffer_around_event():
    worker = IngestionWorker("rtsp://dummy", target_fps=10.0, ring_buffer_sec=10.0)
    base_time = 1000.0
    # Simulate adding frames across time
    for i in range(50):
        # timestamps from 995.0 to 1005.0
        ts = 995.0 + (i * 0.2)
        worker.ring_buffer.append((ts, np.ones((10, 10, 3), dtype=np.uint8) * i))
    
    # Event at base_time 1000.0 with pre=3s, post=3s (997.0 to 1003.0)
    frames = worker.get_buffered_frames_around(event_time=base_time, pre_sec=3.0, post_sec=3.0)
    assert len(frames) > 0
    # Between 997.0 and 1003.0, inclusive with step 0.2
    assert 25 <= len(frames) <= 35

