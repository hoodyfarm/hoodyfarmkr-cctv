"""Unit tests for InferenceWorker and ZoneBehaviorMonitor integration."""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.services.behavior.cattle_behavior_tracker import (
    CLASS_LYING_LATERAL,
    ZoneBehaviorMonitor,
)
from src.services.inference_worker import InferenceWorker
from src.services.ingestion_worker import IngestionWorker


@patch("src.services.inference_worker.YOLO")
def test_inference_worker_triggers_behavior_alert(mock_yolo):
    mock_instance = MagicMock()
    mock_box = MagicMock()
    mock_box.cls = [19]  # cow
    mock_box.conf = [0.9]
    # width=300, height=100 -> aspect ratio 3.0 > 2.3 (측와 보정)
    mock_box.xyxy = [[10.0, 10.0, 310.0, 110.0]]

    mock_box_result = MagicMock()
    mock_box_result.boxes = [mock_box]
    mock_instance.return_value = [mock_box_result]
    mock_instance.names = {0: "person", 19: "cow"}
    mock_yolo.return_value = mock_instance

    ingestion = IngestionWorker("rtsp://dummy", target_fps=10.0)
    monitor = ZoneBehaviorMonitor(zone_id="test_cam")
    worker = InferenceWorker(
        ingestion_worker=ingestion,
        yolo_model_path="yolo11n.pt",
        poll_interval=0.1,
        enable_gemini=False,
        behavior_monitor=monitor,
    )

    dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)

    # 1. 5프레임 공급하여 측와(lying_lateral) 상태 확정
    base_time = 1000.0
    for i in range(5):
        with patch("time.time", return_value=base_time + i * 0.4):
            worker.process_frame(dummy_frame)

    assert monitor.tracks[1].confirmed_posture == CLASS_LYING_LATERAL

    # 2. 15초 경과 후 기립불능 경보 (CATTLE_INVERTED) 격발 확인
    with patch("time.time", return_value=base_time + 18.0):
        res = worker.process_frame(dummy_frame)

    assert res is not None
    assert res["status"] == "event_recorded"
    # detected_targets의 0번째 라벨이 CATTLE_INVERTED로 승격되었는지 확인
    labels = [d["label"] for d in res["yolo_detections"]]
    assert "CATTLE_INVERTED" in labels
