import pytest

@pytest.mark.integration
def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "hoodyfarmkr-cctv"

@pytest.mark.integration
def test_pipeline_capture_and_upload_api(client, monkeypatch):
    from src.services.worker_manager import worker_manager
    monkeypatch.setattr(worker_manager, "trigger_once", lambda: {"status": "filtered"})
    res = client.post("/api/v1/pipeline/capture-and-upload", json={"camera_id": "test_cam_01", "note": "Integration test"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "oci_upload_result" in data

@pytest.mark.integration
def test_gemini_dataset_record_api(client):
    payload = {
        "oci_image_uri": "https://oci.example.com/frame.jpg",
        "system_instruction": "Cattle monitor",
        "user_prompt": "State check",
        "model_response": "Standing"
    }
    res = client.post("/api/v1/gemini/dataset-record", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "jsonl_record" in data
