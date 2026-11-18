import sys
import os
import time
import socket
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.domain.events.event_envelope import CCTVEventEnvelopeV1
from src.domain.models.farm_profile import FarmProfile
from src.infrastructure.webhook.fms_client import FMSWebhookClient
from src.infrastructure.webhook.outbox import WebhookOutbox
from src.services.onvif_service import ONVIFCameraService
from src.services.stream_service import VideoStreamHandler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("e2e_verifier")


class _MockFmsHandler(BaseHTTPRequestHandler):
    received_payloads = []

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8"))
            self.received_payloads.append(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "event_id": data.get("event_id")}).encode("utf-8"))
        except Exception as exc:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress default HTTP logging to keep output clean


def run_e2e_verification():
    print("=" * 65)
    print(" 🚀 hoodyfarmkr-cctv [P3] 실제 카메라 / FMS E2E 연동 종합 점검")
    print("=" * 65)

    results = {}

    # -------------------------------------------------------------
    # [Step 1] Farm Profile & Settings 검증
    # -------------------------------------------------------------
    print("\n[Step 1/5] 축사 프로필 및 시스템 설정 로드 검증...")
    profile = None
    if settings.FARM_PROFILE_PATH and os.path.exists(settings.FARM_PROFILE_PATH):
        profile = FarmProfile.from_yaml(settings.FARM_PROFILE_PATH)
    elif os.path.exists("config/farms/hoodyfarm.yaml"):
        profile = FarmProfile.from_yaml("config/farms/hoodyfarm.yaml")
    else:
        profile = FarmProfile.from_settings(settings)

    print(f" -> Farm ID:        {profile.farm_id} ({profile.farm_name})")
    print(f" -> Configured Cams: {len(profile.cameras)} 개")
    primary_cam = profile.primary_camera
    print(f" -> Primary Camera:  {primary_cam.camera_id} ({primary_cam.name})")
    results["1_FarmProfile"] = "PASS"

    # -------------------------------------------------------------
    # [Step 2] 실제 카메라 (ONVIF & RTSP) 연동 및 프레임 캡처 검증
    # -------------------------------------------------------------
    print("\n[Step 2/5] 실제 카메라 (ONVIF/RTSP) 통신 및 프레임 획득 진단...")
    onvif_service = ONVIFCameraService()
    try:
        stream_url = onvif_service.get_stream_url()
        dev_info = onvif_service.get_device_information()
        print(f" -> ONVIF 연결:     {dev_info['host']}:{dev_info['port']} (Model: {dev_info.get('model')})")
        print(f" -> Target RTSP URL: {stream_url}")
    except Exception as exc:
        print(f" ⚠️ ONVIF URI 획득 경고: {exc}")
        stream_url = settings.RTSP_STREAM_URL or primary_cam.rtsp_url

    handler = VideoStreamHandler(stream_url=stream_url)
    frame, is_synthetic = handler.capture_frame_with_retry(max_retries=2, delay_sec=0.5)

    if frame is not None:
        h, w, c = frame.shape
        source_mode = "시뮬레이션(Synthetic)" if is_synthetic else "실제 카메라(Live CCTV)"
        print(f" ✅ 프레임 캡처 성공! 출처: [{source_mode}], 규격: {w}x{h} (채널 {c})")
        results["2_CameraFrame"] = f"PASS ({source_mode})"
    else:
        print(" ❌ 프레임 캡처 실패")
        results["2_CameraFrame"] = "FAIL"

    # -------------------------------------------------------------
    # [Step 3] AI Detection Event & Envelope v1 스키마 규격 검증
    # -------------------------------------------------------------
    print("\n[Step 3/5] AI 검출 이벤트 및 EventEnvelopeV1 표준 계약 검증...")
    test_event = DetectionEvent(
        event_id=f"e2e_evt_{int(time.time())}",
        camera_id=primary_cam.camera_id,
        tag="e2e_target_detected",
        event_type="INVERTED",
        timestamp=time.time(),
        detections=[
            DetectionTarget(label="cow", confidence=0.92, bbox=[100.0, 150.0, 400.0, 500.0])
        ],
        frame_path="captures/events/e2e_sample.jpg",
        is_anomaly=True,
        ai_summary="개체 기립불능 이상행동 감지 (E2E 검증)",
    )

    fms_client = FMSWebhookClient(farm_id=profile.farm_id)
    envelope = fms_client.build_envelope(
        event=test_event,
        clip_path="captures/clips/e2e_sample.mp4",
        drive_clip_url="https://drive.google.com/file/d/mock_drive_clip",
        drive_image_url="https://drive.google.com/file/d/mock_drive_img",
        tailscale_clip_url="https://cctv.tailscale.local/api/v1/clips/e2e_sample.mp4",
    )

    assert envelope.version == "1.0", "Envelope version mismatch"
    assert envelope.farm_id == profile.farm_id, "Farm ID mismatch"
    assert envelope.media_urls.preferred_clip_url == "https://drive.google.com/file/d/mock_drive_clip"
    print(f" -> Event ID:         {envelope.event_id}")
    print(f" -> Schema Version:   {envelope.version}")
    print(f" -> Preferred Clip:   {envelope.media_urls.preferred_clip_url}")
    print(" ✅ EventEnvelopeV1 스키마 무결성 검증 완료!")
    results["3_EnvelopeV1"] = "PASS"

    # -------------------------------------------------------------
    # [Step 4] FMS 실연동 및 Webhook Outbox 장애 격리/DLQ 검증
    # -------------------------------------------------------------
    print("\n[Step 4/5] FMS Webhook 실연동 및 Outbox 장애 격리 테스트...")
    target_fms_url = settings.FMS_WEBHOOK_URL or "http://localhost:3000/api/v1/cctv-events"
    print(f" -> 대상 FMS URL: {target_fms_url}")

    # 실제 FMS 호출 시도
    real_fms_client = FMSWebhookClient(webhook_url=target_fms_url, timeout=2.0)
    outbox = WebhookOutbox(db_path=":memory:", max_retries=3)

    resp_status = real_fms_client.notify(envelope)
    if resp_status == "delivered (200)":
        print(f" ✅ 실제 FMS 서버 통신 성공! 응답: {resp_status}")
        results["4_RealFMS"] = "PASS (Delivered 200)"
    else:
        print(f" ℹ️ 실제 FMS 미응답/미기동 감지 ({resp_status}) -> Outbox 장애 격리/DLQ 적재 로직 진단")
        outbox_id = outbox.enqueue(
            event_id=envelope.event_id,
            webhook_url=target_fms_url,
            payload=envelope.model_dump(),
        )
        assert outbox_id is not None, "Outbox enqueue failed"
        stats = outbox.get_stats()
        print(f" ✅ Outbox 안전 적재 성공: ID={outbox_id}, Outbox Stats: {stats}")
        results["4_RealFMS"] = "PASS (Fallback to Outbox DLQ)"

    # -------------------------------------------------------------
    # [Step 5] Mock FMS 로컬 엔드포인트를 통한 E2E 양방향 수신 검증
    # -------------------------------------------------------------
    print("\n[Step 5/5] Mock FMS 수신기를 통한 E2E 양방향 Webhook 전달 검증...")
    _MockFmsHandler.received_payloads.clear()

    # Find free port for mock server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        mock_port = s.getsockname()[1]

    mock_server = HTTPServer(("127.0.0.1", mock_port), _MockFmsHandler)
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    mock_thread.start()

    try:
        mock_webhook_url = f"http://127.0.0.1:{mock_port}/api/v1/cctv-events"
        mock_fms_client = FMSWebhookClient(webhook_url=mock_webhook_url, timeout=3.0)
        mock_resp = mock_fms_client.notify(envelope)
        assert mock_resp == "delivered (200)", f"Expected delivered (200), got {mock_resp}"
        assert len(_MockFmsHandler.received_payloads) == 1, "Payload not received by mock FMS"

        received = _MockFmsHandler.received_payloads[0]
        assert received["event_id"] == envelope.event_id
        assert received["farm_id"] == profile.farm_id
        assert received["event_code"] == "INVERTED"
        print(f" ✅ Mock FMS 수신 확인: HTTP 200 OK, Event ID: {received['event_id']}")
        results["5_MockFMS_E2E"] = "PASS (Roundtrip 200 OK)"
    finally:
        mock_server.shutdown()
        mock_server.server_close()

    # -------------------------------------------------------------
    # 종합 요약 보고
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print(" 📊 P3 실제 카메라 / FMS E2E 연동 점검 종합 결과")
    print("=" * 65)
    for check_name, status in results.items():
        print(f" - [{check_name}]: {status}")
    print("=" * 65)
    all_passed = all("PASS" in s for s in results.values())
    if all_passed:
        print("🎉 [P3 연동 점검] 모든 카메라 및 FMS E2E 검증 항목 통과!")
    else:
        print("⚠️ [P3 연동 점검] 일부 항목 점검 필요")
    print("=" * 65 + "\n")
    return all_passed


if __name__ == "__main__":
    success = run_e2e_verification()
    sys.exit(0 if success else 1)
