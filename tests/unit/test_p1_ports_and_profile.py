import os
import time
import pytest
from unittest.mock import MagicMock, patch

from src.core.ports import (
    ClipEncoderPort,
    EventNotifierPort,
    EventPublisherPort,
    FrameSourcePort,
    ObjectStoragePort,
    VisionAnalyzerPort,
    WorkspaceSinkPort,
)
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.domain.events.event_envelope import CCTVEventEnvelopeV1, MediaUrls
from src.domain.models.farm_profile import (
    CameraProfile,
    DetectionRulesProfile,
    FarmProfile,
    NotificationProfile,
    StorageProfile,
)
from src.infrastructure.storage.video_encoder import VideoEncoder
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.pipeline.event_worker import EventWorker
from src.services.gemini_service import GeminiVisionService
from src.services.ingestion_worker import IngestionWorker
from src.services.oci_service import OCIDataPipelineService
from src.infrastructure.google.google_service import GoogleIntegrationService
from src.services.worker_manager import WorkerManager


@pytest.mark.unit
def test_farm_profile_loads_hoodyfarm_yaml(monkeypatch):
    monkeypatch.setenv("FARM_ID", "hoodyfarm_kr")
    monkeypatch.setenv("RTSP_STREAM_URL", "rtsp://cam.local:554/s1")
    monkeypatch.setenv("FMS_WEBHOOK_URL", "https://fms.example.com/hook")
    monkeypatch.setenv("TAILSCALE_HOST_URL", "http://100.64.0.1:8000")

    profile = FarmProfile.from_yaml("config/farms/hoodyfarm.yaml")
    assert profile.farm_id == "hoodyfarm_kr"
    assert profile.primary_camera.camera_id == "cam_01"
    assert profile.primary_camera.rtsp_url == "rtsp://cam.local:554/s1"
    assert profile.rules.species == "cattle"
    assert "INVERTED" in profile.rules.event_codes
    assert profile.notification.fms_webhook_url == "https://fms.example.com/hook"
    assert profile.notification.tailscale_host_url == "http://100.64.0.1:8000"


@pytest.mark.unit
def test_farm_profile_template_and_custom_species_prompt():
    profile = FarmProfile(
        farm_id="swine_farm_01",
        farm_name="Swine Smart Farm",
        cameras=[CameraProfile(camera_id="pig_cam_02", rtsp_url="rtsp://pig:554/live")],
        rules=DetectionRulesProfile(
            species="swine",
            target_classes=["pig", "person"],
            event_codes=["CRUSHING", "FIGHTING", "ESCAPE", "NORMAL"],
        ),
        storage=StorageProfile(media_priority=["oci", "drive", "tailscale"]),
    )
    prompt = profile.rules.build_vision_prompt()
    assert "swine farm" in prompt
    assert "'CRUSHING'" in prompt
    assert "pig, person" in prompt


@pytest.mark.unit
def test_media_urls_priority_resolution():
    media = MediaUrls(
        drive_clip_url="https://drive.google.com/clip.mp4",
        tailscale_clip_url="http://100.64.0.1:8000/clip.mp4",
        oci_clip_url="https://oci.example.com/clip.mp4",
        drive_image_url=None,
        tailscale_image_url="http://100.64.0.1:8000/img.jpg",
        oci_frame_url="https://oci.example.com/img.jpg",
    )
    assert media.resolve_clip_url(["drive", "tailscale", "oci"]) == "https://drive.google.com/clip.mp4"
    assert media.resolve_clip_url(["oci", "drive", "tailscale"]) == "https://oci.example.com/clip.mp4"
    assert media.resolve_snapshot_url(["drive", "tailscale", "oci"]) == "http://100.64.0.1:8000/img.jpg"


@pytest.mark.unit
def test_event_envelope_v1_schema_and_notifier_contract():
    event = DetectionEvent(
        event_id="evt_contract_01",
        camera_id="cam_barn_2",
        tag="cow",
        event_type="CALVING",
        timestamp=time.time() - 5.0,
        detections=[DetectionTarget(label="cow", confidence=0.94)],
        frame_path="/tmp/captures/events/frame_01.jpg",
        is_anomaly=True,
        ai_summary="분만 징후 포착",
        pre_sec=3.0,
        post_sec=3.0,
    )
    client = FMSWebhookClient(
        webhook_url="https://fms.example.com/webhook",
        farm_id="farm_alpha",
        tailscale_host_url="http://100.99.1.2:8000",
        media_priority=["oci", "tailscale", "drive"],
    )
    envelope = client.build_envelope(
        event=event,
        clip_path="/tmp/captures/clips/clip_01.mp4",
        oci_clip_url="https://oci.example.com/clip_01.mp4",
        oci_frame_url="https://oci.example.com/frame_01.jpg",
    )
    assert isinstance(envelope, CCTVEventEnvelopeV1)
    assert envelope.schema_version == "1.0"
    assert envelope.farm_id == "farm_alpha"
    assert envelope.camera_id == "cam_barn_2"
    assert envelope.event_type == "CALVING"
    assert envelope.video_clip_url == "https://oci.example.com/clip_01.mp4"
    assert (
        envelope.tailscale_clip_url
        == "http://100.99.1.2:8000/api/v1/pipeline/captures/view/clips/clip_01.mp4"
    )
    assert envelope.status == "alert"


@pytest.mark.unit
def test_adapters_satisfy_runtime_protocols(tmp_path):
    assert isinstance(IngestionWorker("rtsp://dummy"), FrameSourcePort)
    assert isinstance(GeminiVisionService(), VisionAnalyzerPort)
    assert isinstance(VideoEncoder(output_dir=str(tmp_path)), ClipEncoderPort)
    assert isinstance(OCIDataPipelineService(), ObjectStoragePort)
    assert isinstance(GoogleIntegrationService(), WorkspaceSinkPort)
    assert isinstance(FMSWebhookClient(), EventNotifierPort)


@pytest.mark.unit
@patch("src.services.inference_worker.YOLO")
def test_worker_manager_di_composition_with_custom_profile(mock_yolo):
    profile = FarmProfile(
        farm_id="portable_farm_99",
        farm_name="Portable Test Farm",
        cameras=[CameraProfile(camera_id="cam_west", rtsp_url="rtsp://west:554/1", target_fps=4.0)],
        rules=DetectionRulesProfile(
            species="goat",
            target_classes=["goat", "person"],
            confidence_threshold=0.4,
            cooldown_sec=5.0,
        ),
        notification=NotificationProfile(fms_webhook_url="https://fms.portable.io/events"),
    )
    mock_ingestion = MagicMock(spec=FrameSourcePort)
    mock_ingestion.target_fps = 4.0
    mock_encoder = MagicMock(spec=ClipEncoderPort)
    mock_notifier = MagicMock(spec=EventNotifierPort)
    mock_oci = MagicMock(spec=ObjectStoragePort)
    mock_google = MagicMock(spec=WorkspaceSinkPort)
    mock_vision = MagicMock(spec=VisionAnalyzerPort)

    manager = WorkerManager(
        profile=profile,
        ingestion_worker=mock_ingestion,
        video_encoder=mock_encoder,
        fms_client=mock_notifier,
        oci_service=mock_oci,
        google_service=mock_google,
        vision_service=mock_vision,
    )

    assert isinstance(manager.event_worker, EventPublisherPort)
    assert manager.inference_worker.camera_id == "cam_west"
    assert manager.inference_worker.target_classes == {"goat", "person"}
    assert manager.inference_worker.confidence_threshold == 0.4
    assert manager.inference_worker.event_cooldown_sec == 5.0
    telemetry = manager.get_telemetry()
    assert telemetry["farm_id"] == "portable_farm_99"
    assert telemetry["camera_id"] == "cam_west"
    assert telemetry["species"] == "goat"
