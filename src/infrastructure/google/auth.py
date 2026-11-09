import os
import logging
from typing import Optional, List
from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

class GoogleAuthManager:
    """
    Google Cloud Service Account 인증 관리자.
    - JSON 키 파일 경로를 받아 Service Account Credentials 생성
    - 파일 미존재/오류 시 is_configured = False로 gracefully degradation (Simulation mode) 지원
    - HTTP 요청 시 사용할 Bearer Access Token 획득 및 갱신 지원
    """

    def __init__(
        self,
        service_account_file: Optional[str] = None,
        scopes: Optional[List[str]] = None
    ):
        self.service_account_file = service_account_file
        self.scopes = scopes or DEFAULT_SCOPES
        self.credentials: Optional[service_account.Credentials] = None
        self.is_configured: bool = False
        self._initialize()

    def _initialize(self):
        if not self.service_account_file:
            logger.info("GoogleAuthManager: No service_account_file provided. Simulated/Mock mode enabled.")
            self.is_configured = False
            return

        expanded_path = os.path.expanduser(self.service_account_file)
        if not os.path.exists(expanded_path):
            logger.warning(
                f"GoogleAuthManager: Service account JSON file not found at '{expanded_path}'. "
                "Operating in graceful degradation (Simulation) mode."
            )
            self.is_configured = False
            return

        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                expanded_path,
                scopes=self.scopes
            )
            self.is_configured = True
            logger.info(f"GoogleAuthManager: Service account credentials loaded successfully from {expanded_path}.")
        except Exception as e:
            logger.warning(
                f"GoogleAuthManager: Failed to load service account credentials from '{expanded_path}': {e}. "
                "Falling back to simulated mode."
            )
            self.credentials = None
            self.is_configured = False

    def get_access_token(self) -> Optional[str]:
        """Google API 호출용 유효한 OAuth2 Bearer Access Token 반환"""
        if not self.is_configured or not self.credentials:
            return None

        try:
            if not self.credentials.valid:
                req = Request()
                self.credentials.refresh(req)
            return self.credentials.token
        except Exception as e:
            logger.error(f"GoogleAuthManager: Failed to refresh access token: {e}")
            return None
