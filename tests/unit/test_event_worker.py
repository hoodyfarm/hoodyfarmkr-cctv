import time
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.pipeline.event_worker import EventWorker

def test_event_worker_publish_and_process():
    mock_ingestion = MagicMock()
    mock_ingestion.target_fps = 5.0
    mock_ingestion.get_buffered_frames_around.return_value = [
        np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(15)
    ]

    mock_encoder = MagicMock()
    mock_encoder.encode_clip.return_value = "/tmp/captures/clips/clip_test.mp4"

    mock_fms = MagicMock()
    mock_fms.send_event_alert.return_value = "success (200)"

    mock_oci = MagicMock()
    mock_oci.upload_file_to_oci.return_value = {
        "status": "success",
        "oci_url": "https://objectstorage.ap-seoul-1.oraclecloud.com/test_url"
    }

    worker = EventWorker(
        ingestion_worker=mock_ingestion,
        video_encoder=mock_encoder,
        fms_client=mock_fms,
        oci_service=mock_oci
    )

    event = DetectionEvent(
        event_id="evt_unit_01",
        tag="cow",
        timestamp=time.time() - 4.0,  # 이미 4초 전 발생 (post_sec 0.1 이하로 즉시 처리)
        detections=[DetectionTarget(label="cow", confidence=0.92)],
        frame_path="/tmp/captures/events/event_cow.jpg",
        pre_sec=3.0,
        post_sec=3.0
    )

    worker.start()
    assert worker.publish_event(event) is True
    time.sleep(0.3)
    worker.stop()

    assert worker.total_events_received >= 1
    assert worker.total_clips_created >= 1
    assert worker.total_uploads_completed >= 2  # clip + frame
    assert worker.total_webhooks_sent >= 1
    assert mock_encoder.encode_clip.called
    assert mock_oci.upload_file_to_oci.called
    assert mock_fms.send_event_alert.called

    # FMS 호출 인자 검증 (oci_clip_url 및 oci_frame_url이 올바르게 전달되었는지 확인)
    kwargs = mock_fms.send_event_alert.call_args[1]
    assert kwargs["oci_clip_url"] == "https://objectstorage.ap-seoul-1.oraclecloud.com/test_url"
    assert kwargs["oci_frame_url"] == "https://objectstorage.ap-seoul-1.oraclecloud.com/test_url"
