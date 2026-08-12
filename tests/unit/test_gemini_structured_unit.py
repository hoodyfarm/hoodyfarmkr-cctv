import pytest
from src.schemas.ai_schema import CCTVAnalysisResultSchema, DetectedObject
from src.services.gemini_service import GeminiVisionService

@pytest.mark.unit
def test_cctv_analysis_result_schema_validation():
    obj = DetectedObject(label="intruder", confidence=0.94, location="gate")
    res = CCTVAnalysisResultSchema(
        is_anomaly=True,
        event_type="intrusion",
        confidence_score=0.94,
        detected_objects=[obj],
        summary="야간 펜스 경계 무단 침입자 감지",
        recommended_action="trigger_alarm"
    )
    assert res.is_anomaly is True
    assert res.event_type == "intrusion"
    assert res.confidence_score == 0.94
    assert len(res.detected_objects) == 1
    assert res.detected_objects[0].label == "intruder"
    assert res.recommended_action == "trigger_alarm"

@pytest.mark.unit
def test_gemini_vision_service_simulation_mode():
    service = GeminiVisionService(api_key=None, model_name="gemini-2.5-flash")
    dummy_jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    result = service.analyze_frame_structured(dummy_jpeg_bytes)

    assert isinstance(result, CCTVAnalysisResultSchema)
    assert result.confidence_score > 0.0
    assert isinstance(result.summary, str)
    assert isinstance(result.detected_objects, list)
