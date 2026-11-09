import json
import logging
from typing import Optional, Dict, Any, List
import httpx

from src.infrastructure.google.auth import GoogleAuthManager

logger = logging.getLogger(__name__)

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

class GoogleSheetsClient:
    """
    Google Sheets API v4 연동 클라이언트.
    - FMS 관리용 Google Spreadsheet에 CCTV 이벤트 행(Row) 자동 append
    - 열 구조: [Timestamp | Event ID | Camera ID | Detected Object | Confidence | AI Summary | Video Link | Status]
    - Service Account 미설정 또는 네트워크 오류 시 Graceful degradation (시뮬레이션 모드) 지원
    """

    def __init__(
        self,
        auth_manager: Optional[GoogleAuthManager] = None,
        spreadsheet_id: Optional[str] = None,
        range_name: str = "Events!A:H",
        timeout: float = 20.0
    ):
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.spreadsheet_id = spreadsheet_id
        self.range_name = range_name
        self.timeout = timeout

    @property
    def is_simulation_mode(self) -> bool:
        return not (self.auth_manager and self.auth_manager.is_configured)

    def append_row(
        self,
        row_values: List[Any],
        spreadsheet_id: Optional[str] = None,
        range_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        스프레드시트에 단일 행을 append.
        """
        target_sheet = spreadsheet_id or self.spreadsheet_id
        target_range = range_name or self.range_name

        if self.is_simulation_mode:
            logger.info(
                f"GoogleSheetsClient [Simulation]: Appended row to sheet [{target_sheet} / {target_range}]: {row_values}"
            )
            return {
                "status": "success",
                "mode": "simulation",
                "spreadsheet_id": target_sheet,
                "range": target_range,
                "values": row_values,
                "updated_rows": 1
            }

        if not target_sheet:
            logger.warning("GoogleSheetsClient: spreadsheet_id not provided. Skipping append.")
            return {
                "status": "skipped",
                "reason": "missing_spreadsheet_id"
            }

        token = self.auth_manager.get_access_token()
        if not token:
            logger.warning("GoogleSheetsClient: Failed to obtain valid access token. Falling back to simulation.")
            return {
                "status": "success",
                "mode": "simulation_fallback",
                "spreadsheet_id": target_sheet,
                "range": target_range,
                "values": row_values,
                "updated_rows": 1
            }

        url = f"{SHEETS_API_BASE}/{target_sheet}/values/{target_range}:append"
        params = {
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS"
        }
        body = {
            "values": [row_values]
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, params=params, json=body, headers=headers)
                if res.status_code in (200, 201):
                    data = res.json()
                    logger.info(
                        f"GoogleSheetsClient: Successfully appended row to {target_sheet} ({target_range})"
                    )
                    return {
                        "status": "success",
                        "mode": "real",
                        "response": data,
                        "updated_rows": 1
                    }
                else:
                    logger.error(f"GoogleSheetsClient: Sheets API error {res.status_code}: {res.text}")
                    return {
                        "status": "error",
                        "mode": "real",
                        "status_code": res.status_code,
                        "detail": res.text
                    }
        except Exception as e:
            logger.error(f"GoogleSheetsClient: Exception appending row: {e}")
            return {
                "status": "error",
                "mode": "real",
                "error": str(e)
            }
