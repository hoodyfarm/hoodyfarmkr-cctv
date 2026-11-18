import os
import time
import pytest
from src.core.ports import ObjectStoragePort
from src.services.oci_service import OCIDataPipelineService
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.domain.events.event_envelope import CCTVEventEnvelopeV1, MediaUrls
from src.infrastructure.webhook.fms_client import FMSWebhookClient

@pytest.mark.asyncio
async def test_object_storage_port_protocol_and_upload_and_sign(tmp_path):
    service = OCIDataPipelineService()
    # Confirm protocol compliance
    assert isinstance(service, ObjectStoragePort)

    # Test file upload + signed URL generation
    test_clip = tmp_path / "event_clip.mp4"
    test_clip.write_bytes(b"\x00\x00\x00 ftypisom")

    res = await service.upload_and_sign(
        str(test_clip),
        object_name="clips/cattle/test_clip.mp4",
        expiry_days=5
    )
    assert res["status"] in ["simulated", "success"]
    assert "signed_url" in res
    assert "media_signed_url" in res
    assert res["expiry_days"] == 5
    assert "/clips/cattle/test_clip.mp4" in res["signed_url"]

    # Test bytes upload + signed URL generation
    byte_res = await service.upload_and_sign(
        b"mock_snapshot_bytes",
        object_name="events/cattle/snapshot.jpg",
        expiry_days=3
    )
    assert byte_res["status"] in ["simulated", "success"]
    assert "signed_url" in byte_res
    assert byte_res["expiry_days"] == 3

@pytest.mark.unit
def test_event_envelope_signed_url_injection_and_priority():
    event = DetectionEvent(
        event_id="evt_sign_001",
        camera_id="cam_main",
        tag="cow",
        event_type="CALVING",
        timestamp=time.time(),
        detections=[DetectionTarget(label="cow", confidence=0.95)],
        frame_path="/tmp/frame.jpg",
        is_anomaly=True,
    )

    client = FMSWebhookClient(
        webhook_url="https://fms.example.com/api/v1/events",
        farm_id="hoody_test",
        media_priority=["signed_url", "drive", "tailscale", "oci"],
    )

    mock_par_clip = "https://objectstorage.ap-seoul-1.oraclecloud.com/p/token123/n/ns/b/cctv-raw-videos/o/clip.mp4"
    mock_par_img = "https://objectstorage.ap-seoul-1.oraclecloud.com/p/token456/n/ns/b/cctv-refined/o/frame.jpg"

    envelope = client.build_envelope(
        event=event,
        clip_path="/tmp/clip.mp4",
        oci_clip_url=mock_par_clip,
        oci_frame_url=mock_par_img,
        media_signed_url=mock_par_clip,
        frame_signed_url=mock_par_img,
        drive_clip_url="https://drive.google.com/clip.mp4",
    )

    # Check top-level media_signed_url and frame_signed_url
    assert envelope.media_signed_url == mock_par_clip
    assert envelope.frame_signed_url == mock_par_img
    # Check media_urls structured sub-model
    assert envelope.media_urls is not None
    assert envelope.media_urls.media_signed_url == mock_par_clip
    assert envelope.media_urls.frame_signed_url == mock_par_img
    # Because priority is ["signed_url", ...], video_clip_url should resolve to signed_url
    assert envelope.video_clip_url == mock_par_clip
    assert envelope.snapshot_url == mock_par_img
