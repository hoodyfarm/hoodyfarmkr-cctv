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
