import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.config import Settings, settings
from src.main import app
from src.services.worker_manager import worker_manager


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "s3cret-key")
    return TestClient(app)


@pytest.mark.unit
def test_health_is_public(secured):
    assert secured.get("/health").status_code == 200


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/api/v1/pipeline/status", "/api/v1/camera/info"])
def test_protected_routes_reject_missing_or_wrong_key(secured, path):
    assert secured.get(path).status_code == 401
    assert secured.get(path, headers={"X-API-Key": "wrong"}).status_code == 401


@pytest.mark.unit
def test_protected_route_accepts_valid_key(secured):
    res = secured.get("/api/v1/pipeline/status", headers={"X-API-Key": "s3cret-key"})
    assert res.status_code == 200
    assert res.json()["farm_id"] == settings.FARM_ID


@pytest.mark.unit
def test_media_view_is_public_and_blocks_traversal(secured):
    assert secured.get("/api/v1/pipeline/captures/view/clips/nope.mp4").status_code == 404
    assert secured.get("/api/v1/pipeline/captures/view/clips/..%5Csecret.txt").status_code == 400
    assert secured.get("/api/v1/pipeline/captures/view/other/x.jpg").status_code == 400


@pytest.mark.unit
def test_trigger_returns_503_when_no_frame(secured, monkeypatch):
    monkeypatch.setattr(worker_manager, "trigger_once", lambda: None)
    res = secured.post("/api/v1/pipeline/trigger", headers={"X-API-Key": "s3cret-key"})
    assert res.status_code == 503


@pytest.mark.unit
def test_trigger_uses_unified_worker_pipeline(secured, monkeypatch):
    monkeypatch.setattr(worker_manager, "trigger_once", lambda: {"status": "filtered"})
    res = secured.post("/api/v1/pipeline/trigger", headers={"X-API-Key": "s3cret-key"})
    assert res.status_code == 200
    assert res.json() == {"status": "filtered"}


@pytest.mark.unit
def test_production_requires_api_key_and_db_credentials():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", _env_file=None)
    ok = Settings(ENVIRONMENT="production", API_KEY="k", POSTGRES_PASSWORD="p", _env_file=None)
    assert ok.is_production


@pytest.mark.unit
def test_no_farm_specific_defaults():
    s = Settings(_env_file=None)
    assert s.TAILSCALE_HOST_URL is None
    assert s.FMS_WEBHOOK_URL is None
    assert s.POSTGRES_PASSWORD == ""
    assert s.cors_origins == []
