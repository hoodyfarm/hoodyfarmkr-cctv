import pytest
from src.db.models import CCTVDevice, FrameLog, AIAnalysisResult, AlertEvent

@pytest.mark.unit
def test_cctv_device_model_instantiation():
    device = CCTVDevice(
        name="Test Camera",
        host="192.168.1.50",
        port=80,
        rtsp_url="rtsp://admin:pass@192.168.1.50:554/stream1"
    )
    assert device.name == "Test Camera"
    assert device.host == "192.168.1.50"
    assert device.port == 80
    assert repr(device) == "<CCTVDevice(id=None, name='Test Camera', host='192.168.1.50')>"

@pytest.mark.unit
def test_ai_analysis_result_model_instantiation():
    res = AIAnalysisResult(
        is_anomaly=True,
        event_type="intrusion",
        confidence_score=0.92,
        detected_objects=[{"label": "person", "confidence": 0.92}],
        summary="Intruder detected"
    )
    assert res.is_anomaly is True
    assert res.event_type == "intrusion"
    assert res.confidence_score == 0.92
    assert len(res.detected_objects) == 1
    assert repr(res) == "<AIAnalysisResult(id=None, event_type='intrusion', is_anomaly=True)>"
