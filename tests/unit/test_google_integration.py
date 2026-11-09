import os
import json
import pytest
from unittest.mock import MagicMock, patch

from src.infrastructure.google.auth import GoogleAuthManager
from src.infrastructure.google.drive_client import GoogleDriveClient
from src.infrastructure.google.sheets_client import GoogleSheetsClient
from src.infrastructure.google.google_service import GoogleIntegrationService
from src.domain.events.detection_event import DetectionEvent, DetectionTarget
from src.pipeline.event_worker import EventWorker

def test_google_auth_manager_graceful_degradation_nonexistent_file():
    """자격 증명 파일 미설정/부존재 시 mock/simulation 모드로 graceful degradation 검증"""
    auth = GoogleAuthManager(service_account_file="nonexistent_key.json")
    assert auth.is_configured is False
    assert auth.credentials is None
    assert auth.get_access_token() is None

def test_google_auth_manager_none_file():
    """자격 증명 파일 경로 미제공 시 시뮬레이션 모드 유지"""
    auth = GoogleAuthManager(service_account_file=None)
    assert auth.is_configured is False
    assert auth.get_access_token() is None

def test_google_drive_client_simulation_mode(tmp_path):
    """Google Drive 클라이언트 시뮬레이션 모드 업로드 검증"""
    test_file = tmp_path / "test_clip.mp4"
    test_file.write_text("dummy video content")

    auth = GoogleAuthManager(service_account_file=None)
    drive_client = GoogleDriveClient(auth_manager=auth, folder_id="fake_folder_123")
    
    assert drive_client.is_simulation_mode is True
    res = drive_client.upload_file(file_path=str(test_file))

    assert res["status"] == "success"
    assert res["mode"] == "simulation"
    assert "https://drive.google.com/file/d/" in res["web_view_link"]
    assert res["folder_id"] == "fake_folder_123"

def test_google_sheets_client_simulation_mode():
    """Google Sheets 클라이언트 시뮬레이션 모드 append_row 검증"""
    auth = GoogleAuthManager(service_account_file=None)
    sheets_client = GoogleSheetsClient(
        auth_manager=auth,
        spreadsheet_id="test_sheet_id",
        range_name="Events!A:H"
    )

    assert sheets_client.is_simulation_mode is True
    row = ["2026-11-09 11:00:00 UTC", "evt_123", "cam_01", "cow", "0.95", "AI alert", "http://drive/link", "CONFIRMED"]
    res = sheets_client.append_row(row_values=row)

    assert res["status"] == "success"
    assert res["mode"] == "simulation"
    assert res["values"] == row
    assert res["updated_rows"] == 1

def test_google_integration_service_pipeline_format(tmp_path):
    """
    통합 서비스:
    열 구조 [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status] 검증
    """
    test_clip = tmp_path / "event_clip.mp4"
    test_clip.write_text("mp4 content")

    service = GoogleIntegrationService(
        service_account_file=None,
        drive_folder_id="drive_folder_fms",
        sheet_id="fms_sheet_fms",
        sheet_range="Events!A:H"
    )

    result = service.process_event_record(
        event_id="evt_cow_001",
        camera_id="cam_barn_01",
        detected_object="cow",
        confidence=0.942,
        ai_summary="소 활동 및 이동 감지",
        clip_path=str(test_clip),
        oci_clip_url="https://objectstorage.oci.com/raw.mp4",
        timestamp=1762680000.0,
        status="CONFIRMED"
    )

    assert result["status"] == "success"
    assert "drive_result" in result
    assert "sheet_result" in result
    
    row_values = result["row_values"]
    assert len(row_values) == 8
    # [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status]
    assert "UTC" in row_values[0]
    assert row_values[1] == "evt_cow_001"
    assert row_values[2] == "cam_barn_01"
    assert row_values[3] == "cow"
    assert row_values[4] == "0.94"
    assert row_values[5] == "소 활동 및 이동 감지"
    assert "drive.google.com" in row_values[6]
    assert row_values[7] == "CONFIRMED"

def test_google_drive_and_sheets_real_api_mock(tmp_path):
    """Google Drive 및 Sheets 실제 API 호출 분기 모의(Mocking) 검증"""
    test_file = tmp_path / "mock_file.mp4"
    test_file.write_text("data")

    mock_auth = MagicMock()
    mock_auth.is_configured = True
    mock_auth.get_access_token.return_value = "mock_access_token"

    # Drive Real API mock
    drive_client = GoogleDriveClient(auth_manager=mock_auth, folder_id="target_folder")
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "real_file_999",
            "webViewLink": "https://drive.google.com/file/d/real_file_999/view"
        }
        mock_post.return_value = mock_resp

        drive_res = drive_client.upload_file(file_path=str(test_file))
        assert drive_res["status"] == "success"
        assert drive_res["mode"] == "real"
        assert drive_res["file_id"] == "real_file_999"

    # Sheets Real API mock
    sheets_client = GoogleSheetsClient(
        auth_manager=mock_auth,
        spreadsheet_id="real_sheet_id",
        range_name="Events!A:H"
    )
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"updates": {"updatedRows": 1}}
        mock_post.return_value = mock_resp

        sheet_res = sheets_client.append_row(row_values=["val1", "val2"])
        assert sheet_res["status"] == "success"
        assert sheet_res["mode"] == "real"
        assert sheet_res["updated_rows"] == 1

def test_event_worker_google_integration():
    """EventWorker 파이프라인에서 Google Drive 업로드 및 Sheets append_row 자동 연동 검증"""
    mock_ingestion = MagicMock()
    mock_ingestion.target_fps = 5.0
    mock_ingestion.get_buffered_frames_around.return_value = ["dummy_frame"] * 5

    mock_encoder = MagicMock()
    mock_encoder.encode_clip.return_value = "/tmp/captures/clips/clip_cow.mp4"

    mock_fms = MagicMock()
    mock_fms.send_event_alert.return_value = "success (200)"

    mock_oci = MagicMock()
    mock_oci.upload_file_to_oci.return_value = {
        "status": "success",
        "oci_url": "https://oci.example.com/clip_cow.mp4"
    }

    mock_google = MagicMock()
    mock_google.process_event_record.return_value = {
        "status": "success",
        "drive_result": {"status": "success", "drive_url": "https://drive.google.com/test"},
        "sheet_result": {"status": "success", "updated_rows": 1},
        "video_link": "https://drive.google.com/test",
        "row_values": ["2026-11-09", "evt_cow_99", "cam_01", "cow", "0.98", "AI Summary", "https://drive.google.com/test", "CONFIRMED"]
    }

    worker = EventWorker(
        ingestion_worker=mock_ingestion,
        video_encoder=mock_encoder,
        fms_client=mock_fms,
        oci_service=mock_oci,
        google_service=mock_google
    )

    event = DetectionEvent(
        event_id="evt_cow_99",
        camera_id="cam_barn_02",
        tag="cow",
        timestamp=100.0,
        detections=[DetectionTarget(label="cow", confidence=0.98)],
        frame_path="/tmp/captures/events/frame_cow.jpg",
        ai_summary="건강한 소 감지",
        is_anomaly=False,
        pre_sec=0.0,
        post_sec=0.0
    )

    worker._process_single_event(event)

    assert mock_google.process_event_record.called
    kwargs = mock_google.process_event_record.call_args[1]
    assert kwargs["event_id"] == "evt_cow_99"
    assert kwargs["camera_id"] == "cam_barn_02"
    assert kwargs["detected_object"] == "cow"
    assert kwargs["confidence"] == 0.98
    assert kwargs["ai_summary"] == "건강한 소 감지"
    assert kwargs["clip_path"] == "/tmp/captures/clips/clip_cow.mp4"
    assert kwargs["oci_clip_url"] == "https://oci.example.com/clip_cow.mp4"
    assert kwargs["status"] == "CONFIRMED"

    assert worker.total_sheets_recorded == 1
    assert worker.total_drive_uploads == 1
    assert worker.total_webhooks_sent == 1
