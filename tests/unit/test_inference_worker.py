import pytest
import time
import numpy as np
from unittest.mock import MagicMock, patch
from src.services.ingestion_worker import IngestionWorker
from src.services.inference_worker import InferenceWorker

def test_inference_worker_initialization():
    ingestion = IngestionWorker("rtsp://dummy")
    worker = InferenceWorker(ingestion, yolo_model_path="yolo11n.pt", poll_interval=0.5)
    
    assert worker.poll_interval == 0.5
    assert worker.total_inferences == 0
    assert "cow" in worker.target_classes
    assert worker._running is False

@patch("src.services.inference_worker.YOLO")
def test_inference_worker_filtering_empty_frame(mock_yolo):
    # Mock YOLO returning 0 boxes
    mock_instance = MagicMock()
    mock_box_result = MagicMock()
    mock_box_result.boxes = []
    mock_instance.return_value = [mock_box_result]
    mock_instance.names = {0: "person", 19: "cow"}
    mock_yolo.return_value = mock_instance

    ingestion = IngestionWorker("rtsp://dummy")
    worker = InferenceWorker(ingestion, yolo_model_path="yolo11n.pt", poll_interval=0.1, enable_gemini=False)
    
    # Put a dummy frame into ingestion queue
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    ingestion.frame_queue.put(dummy_frame)
    
    worker.start()
    time.sleep(0.3)
    worker.stop()
    
    assert worker.total_inferences >= 1
    assert worker.filtered_count >= 1
    assert worker.last_result["status"] == "filtered"

@patch("src.services.inference_worker.YOLO")
def test_inference_worker_detect_target_and_clip_trigger(mock_yolo):
    # Mock YOLO returning cow
    mock_instance = MagicMock()
    mock_box = MagicMock()
    mock_box.cls = [19]
    mock_box.conf = [0.85]
    mock_box_result = MagicMock()
    mock_box_result.boxes = [mock_box]
    mock_instance.return_value = [mock_box_result]
    mock_instance.names = {0: "person", 19: "cow"}
    mock_yolo.return_value = mock_instance

    ingestion = IngestionWorker("rtsp://dummy", target_fps=10.0)
    worker = InferenceWorker(ingestion, yolo_model_path="yolo11n.pt", poll_interval=0.1, enable_gemini=False)
    worker.post_event_sec = 0.1  # 빠른 테스트를 위해 post_event 대기 시간 단축
    
    # 링 버퍼에 프레임 모의 누적
    now = time.time()
    for i in range(10):
        ingestion.ring_buffer.append((now - 1.0 + (i * 0.1), np.zeros((100, 100, 3), dtype=np.uint8)))
    
    # Ingestion 큐에 프레임 전달
    ingestion.frame_queue.put(np.zeros((100, 100, 3), dtype=np.uint8))
    
    worker.start()
    time.sleep(0.5)
    worker.stop()
    
    assert worker.total_inferences >= 1
    assert worker.event_saved_count >= 1
    assert worker.last_result["status"] == "event_recorded"
    assert worker.last_result["yolo_detections"][0]["label"] == "cow"

