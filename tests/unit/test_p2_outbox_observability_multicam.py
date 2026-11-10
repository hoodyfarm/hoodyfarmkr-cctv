import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.config import settings
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.domain.events.event_envelope import CCTVEventEnvelopeV1
from src.domain.models.farm_profile import (
    CameraProfile,
    DetectionRulesProfile,
    FarmProfile,
    NotificationProfile,
)
from src.infrastructure.webhook.outbox import WebhookOutbox
from src.main import app
from src.pipeline.event_worker import EventWorker
from src.services.worker_manager import WorkerManager


def _make_sample_envelope(event_id: str = "evt_outbox_01", farm_id: str = "farm_a") -> CCTVEventEnvelopeV1:
    event = DetectionEvent(
        event_id=event_id,
        camera_id="cam_01",
        tag="cow",
        event_type="INVERTED",
        detections=[DetectionTarget(label="cow", confidence=0.91)],
        frame_path="/tmp/frame.jpg",
        is_anomaly=True,
        ai_summary="기립불능 감지",
    )
    return CCTVEventEnvelopeV1.from_event(event=event, farm_id=farm_id)


@pytest.mark.unit
def test_webhook_outbox_retry_and_dlq_lifecycle(tmp_path):
    db_file = str(tmp_path / "outbox_test.sqlite3")
    outbox = WebhookOutbox(db_path=db_file, max_attempts=3, base_backoff_sec=0.01)

    env = _make_sample_envelope("evt_dlq_1")
    outbox.enqueue(env, error="error (timeout)", initial_attempts=1)

    stats = outbox.get_stats()
    assert stats["pending"] == 1
    assert stats["dlq"] == 0

    # Wait briefly so next_retry_at is due, then fail twice -> should move to DLQ (attempts 1 -> 2 -> 3)
    time.sleep(0.03)
    res1 = outbox.process_due(sender=lambda _: "failed (502)", now=time.time() + 10.0)
    assert res1["retried"] == 1
    assert outbox.get_stats()["pending"] == 1

    res2 = outbox.process_due(sender=lambda _: "failed (503)", now=time.time() + 20.0)
    assert res2["dlq"] == 1
    assert outbox.get_stats()["dlq"] == 1
    assert outbox.get_stats()["pending"] == 0

    # Requeue DLQ and succeed
    requeued = outbox.requeue_dlq()
    assert requeued == 1
    assert outbox.get_stats()["pending"] == 1

    res3 = outbox.process_due(sender=lambda _: "success (200)", now=time.time() + 30.0)
    assert res3["delivered"] == 1
    assert outbox.get_stats()["delivered"] == 1
    assert outbox.get_stats()["pending"] == 0


@pytest.mark.unit
def test_event_worker_enqueues_to_outbox_on_webhook_failure(tmp_path):
    db_file = str(tmp_path / "ew_outbox.sqlite3")
    outbox = WebhookOutbox(db_path=db_file, max_attempts=3, base_backoff_sec=0.01)

    mock_ing = MagicMock()
    mock_ing.target_fps = 5.0
    mock_ing.get_buffered_frames_around.return_value = []

    mock_enc = MagicMock()
    mock_fms = MagicMock()
    mock_fms.send_event_alert.return_value = "error (connection refused)"
    mock_oci = MagicMock()
    mock_google = MagicMock()
    mock_google.process_event_record.return_value = {"status": "skipped"}

    ew = EventWorker(
        ingestion_worker=mock_ing,
        video_encoder=mock_enc,
        fms_client=mock_fms,
        oci_service=mock_oci,
        google_service=mock_google,
        outbox=outbox,
    )
    event = DetectionEvent(
        event_id="evt_fail_99",
        camera_id="cam_01",
        tag="cow",
        event_type="ESCAPE",
        timestamp=time.time() - 5.0,
        detections=[DetectionTarget(label="cow", confidence=0.88)],
        frame_path="",
        is_anomaly=True,
    )
    ew._process_single_event(event)
    assert ew.total_webhooks_queued == 1
    assert outbox.get_stats()["pending"] == 1


@pytest.mark.unit
@patch("src.services.inference_worker.YOLO")
def test_multi_camera_worker_manager_and_event_routing(mock_yolo, tmp_path):
    profile = FarmProfile(
        farm_id="multi_barn_farm",
        farm_name="Multi Barn Farm",
        cameras=[
            CameraProfile(camera_id="cam_barn_1", rtsp_url="rtsp://b1:554/s", target_fps=5.0),
            CameraProfile(camera_id="cam_barn_2", rtsp_url="rtsp://b2:554/s", target_fps=4.0),
        ],
        rules=DetectionRulesProfile(species="cattle", target_classes=["cow"]),
        notification=NotificationProfile(fms_webhook_url=""),
    )
    outbox = WebhookOutbox(db_path=str(tmp_path / "mc_outbox.sqlite3"))
    manager = WorkerManager(profile=profile, outbox=outbox)

    assert len(manager.ingestion_workers) == 2
    assert len(manager.inference_workers) == 2
    assert set(manager.ingestion_workers.keys()) == {"cam_barn_1", "cam_barn_2"}
    assert manager.event_worker.resolve_frame_source("cam_barn_2") is manager.ingestion_workers["cam_barn_2"]

    telemetry = manager.get_telemetry()
    assert telemetry["camera_count"] == 2
    assert "cam_barn_1" in telemetry["cameras"]
    assert "cam_barn_2" in telemetry["cameras"]


@pytest.mark.unit
def test_observability_correlation_id_and_prometheus_metrics(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "obs-secret")
    client = TestClient(app)

    # 1. /health returns pipeline & outbox summary + echoes X-Correlation-ID
    res_h = client.get("/health", headers={"X-Correlation-ID": "cid-test-123"})
    assert res_h.status_code == 200
    assert res_h.headers.get("X-Correlation-ID") == "cid-test-123"
    body = res_h.json()
    assert "pipeline" in body
    assert "outbox" in body["pipeline"]

    # 2. /metrics requires auth and serves Prometheus text format
    assert client.get("/metrics").status_code == 401
    res_m = client.get("/metrics", headers={"X-API-Key": "obs-secret"})
    assert res_m.status_code == 200
    assert "cctv_inferences_total" in res_m.text
    assert "cctv_outbox_events" in res_m.text
    assert "cctv_camera_connected" in res_m.text

    # 3. /api/v1/pipeline/outbox and /outbox/retry endpoints
    res_o = client.get("/api/v1/pipeline/outbox", headers={"X-API-Key": "obs-secret"})
    assert res_o.status_code == 200
    assert "pending" in res_o.json()["outbox"]

    res_r = client.post("/api/v1/pipeline/outbox/retry", headers={"X-API-Key": "obs-secret"})
    assert res_r.status_code == 200
    assert "flush_result" in res_r.json()
