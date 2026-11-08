import json
import pytest
from src.services.gemini_service import GeminiDatasetPipeline

@pytest.mark.unit
def test_gemini_jsonl_record_generation():
    pipeline = GeminiDatasetPipeline()
    record = pipeline.generate_fine_tuning_jsonl_entry(
        oci_image_uri="https://objectstorage.oci.oraclecloud.com/frame.jpg",
        system_instruction="Cattle monitor",
        user_prompt="Analyze health",
        model_response="Normal"
    )
    parsed = json.loads(record)
    assert len(parsed["messages"]) == 3
    assert parsed["messages"][0]["content"] == "Cattle monitor"

@pytest.mark.unit
def test_gemini_multimodal_prompt_formatting():
    pipeline = GeminiDatasetPipeline()
    payload = pipeline.format_multimodal_prompt("https://objectstorage.oci.oraclecloud.com/frame.jpg", "Analyze frame")
    assert "gemini-" in payload["model"]
    assert len(payload["contents"][0]["parts"]) == 2
