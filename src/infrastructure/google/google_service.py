import logging
import datetime
from typing import Optional, Dict, Any, List

from src.config import settings
from src.infrastructure.google.auth import GoogleAuthManager
from src.infrastructure.google.drive_client import GoogleDriveClient
from src.infrastructure.google.sheets_client import GoogleSheetsClient

logger = logging.getLogger(__name__)

class GoogleIntegrationService:
    """
    Google Drive 영상 업로드 및 Google Spreadsheet FMS 자동 기록 통합 파이프라인 서비스.
    - 열 구조: [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status]
    - Drive 업로드 결과 또는 OCI 링크를 활용하여 통합 영상 링크 생성
    - 외부 FMS 시스템과의 이중화(Webhook + Google Sheets) 체계 보장
    """

    def __init__(
        self,
        auth_manager: Optional[GoogleAuthManager] = None,
        drive_client: Optional[GoogleDriveClient] = None,
        sheets_client: Optional[GoogleSheetsClient] = None,
        service_account_file: Optional[str] = None,
        drive_folder_id: Optional[str] = None,
        sheet_id: Optional[str] = None,
        sheet_range: Optional[str] = None,
        enabled: Optional[bool] = None
    ):
        self.enabled = enabled if enabled is not None else getattr(settings, "GOOGLE_INTEGRATION_ENABLED", True)
        sa_file = service_account_file or getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", None)
        self.auth_manager = auth_manager or GoogleAuthManager(service_account_file=sa_file)

        folder_id = drive_folder_id or getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)
        self.drive_client = drive_client or GoogleDriveClient(
            auth_manager=self.auth_manager,
            folder_id=folder_id
        )

        spreadsheet_id = sheet_id or getattr(settings, "GOOGLE_SHEET_ID", None)
        s_range = sheet_range or getattr(settings, "GOOGLE_SHEET_RANGE", "Events!A:H")
        self.sheets_client = sheets_client or GoogleSheetsClient(
            auth_manager=self.auth_manager,
            spreadsheet_id=spreadsheet_id,
            range_name=s_range
        )

    def process_event_record(
        self,
        event_id: str,
        camera_id: str,
        detected_object: str,
        confidence: float,
        ai_summary: Optional[str] = None,
        clip_path: Optional[str] = None,
        frame_path: Optional[str] = None,
        oci_clip_url: Optional[str] = None,
        timestamp: Optional[float] = None,
        status: str = "CONFIRMED",
        event_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        1. clip_path 및 frame_path가 존재할 경우 Google Drive 업로드 수행 (Tier 1 SSOT 미디어)
        2. Video Link 결정 (Google Drive Link 우선, 없을 시 OCI Video URL, 로컬 경로 순)
        3. FMS Google Spreadsheet에 8개 표준 필드 Row 추가:
           [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status]
        """
        if not self.enabled:
            logger.info("GoogleIntegrationService: Disabled by configuration. Skipping.")
            return {"status": "disabled"}

        drive_result: Optional[Dict[str, Any]] = None
        drive_url: Optional[str] = None
        drive_image_result: Optional[Dict[str, Any]] = None
        drive_image_url: Optional[str] = None

        # 1. Google Drive 클립 영상 업로드 (anyoneWithLink 자동 부여)
        if clip_path:
            try:
                drive_result = self.drive_client.upload_file(file_path=clip_path, make_public=True)
                if drive_result and drive_result.get("status") == "success":
                    drive_url = drive_result.get("drive_url") or drive_result.get("web_view_link")
            except Exception as e:
                logger.warning(f"GoogleIntegrationService: Drive clip upload exception for [{event_id}]: {e}")

        # 1-B. Google Drive 스냅샷 이미지 업로드
        if frame_path:
            try:
                drive_image_result = self.drive_client.upload_file(file_path=frame_path, make_public=True)
                if drive_image_result and drive_image_result.get("status") == "success":
                    drive_image_url = drive_image_result.get("drive_url") or drive_image_result.get("web_view_link")
            except Exception as e:
                logger.warning(f"GoogleIntegrationService: Drive frame upload exception for [{event_id}]: {e}")

        # 2. 대표 Video Link 결정 (Drive -> OCI -> Local Path)
        video_link = drive_url or oci_clip_url or (clip_path if clip_path else "N/A")

        # 3. 타임스탬프 포맷팅 (ISO 8601 UTC / Local string)
        if timestamp:
            dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            formatted_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 4. 시트 열 포맷 [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status]
        # Detected Object 열에 단독 event_type 코드(INVERTED, CALVING 등)를 우선 기록하여 시트/AppSheet 파서 100% 무결점 보장
        object_column_value = event_type or detected_object

        row_values = [
            formatted_time,
            event_id,
            camera_id,
            object_column_value,
            f"{confidence:.2f}",
            ai_summary or f"{detected_object} detected",
            video_link,
            status
        ]

        sheet_result = self.sheets_client.append_row(row_values=row_values)

        return {
            "status": "success",
            "drive_result": drive_result,
            "drive_image_result": drive_image_result,
            "drive_clip_url": drive_url,
            "drive_image_url": drive_image_url,
            "sheet_result": sheet_result,
            "video_link": video_link,
            "row_values": row_values
        }
