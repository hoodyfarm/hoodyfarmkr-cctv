import os
import tempfile
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.services.clip_service import ClipService

def test_clip_service_generate_mp4_clip():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = ClipService(output_dir=tmpdir)
        
        # 10 dummy frames
        frames = [np.zeros((120, 160, 3), dtype=np.uint8) for _ in range(10)]
        clip_path = service.generate_mp4_clip(frames, tag="cow", fps=5.0)
        
        assert clip_path is not None
        assert os.path.exists(clip_path)
        assert clip_path.endswith(".mp4")
        assert os.path.getsize(clip_path) > 0

def test_clip_service_generate_mp4_empty_frames():
    with tempfile.TemporaryDirectory() as tmpdir:
        service = ClipService(output_dir=tmpdir)
        clip_path = service.generate_mp4_clip([], tag="empty")
        assert clip_path is None

@patch("httpx.Client.post")
def test_clip_service_send_fms_webhook(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    service = ClipService()
    result = service.send_fms_webhook(
        event_type="cow_detected",
        detections=[{"label": "cow", "confidence": 0.88}],
        clip_path="dummy.mp4",
        webhook_url="http://test-fms:3000/api/v1/cctv-events"
    )

    assert "success (200)" in result
    assert mock_post.called
    kwargs = mock_post.call_args[1]
    assert kwargs["json"]["event_type"] == "cow_detected"
    assert kwargs["json"]["detections"][0]["label"] == "cow"
    assert kwargs["json"]["clip"]["file_name"] == "dummy.mp4"
