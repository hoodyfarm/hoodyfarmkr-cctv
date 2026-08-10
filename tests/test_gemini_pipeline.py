import json
from src.services.gemini_service import GeminiDatasetPipeline

def test_gemini_jsonl_formatting():
    pipeline = GeminiDatasetPipeline()
    jsonl_str = pipeline.generate_fine_tuning_jsonl_entry(
        oci_image_uri="https://objectstorage.oci.oraclecloud.com/n/ns/b/bucket/o/frame.jpg",
        system_instruction="Monitor cattle",
        user_prompt="Assess health",
        model_response="Cattle healthy"
    )
    parsed = json.loads(jsonl_str)
    assert "messages" in parsed
    assert len(parsed["messages"]) == 3
