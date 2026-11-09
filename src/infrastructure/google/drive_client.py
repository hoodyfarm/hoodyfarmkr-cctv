import os
import json
import logging
from typing import Optional, Dict, Any
import httpx

from src.infrastructure.google.auth import GoogleAuthManager

logger = logging.getLogger(__name__)

DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3/files"

class GoogleDriveClient:
    """
    Google Drive API v3 연동 클라이언트.
    - 영상 클립(.mp4) 및 이벤트 프레임(.jpg)을 Google Drive 지정 폴더에 업로드
    - Service Account 미설정 또는 네트워크 오류 시 Graceful degradation (시뮬레이션 모드) 지원
    - Web View Link / Drive Link 생성 반환
    """

    def __init__(
        self,
        auth_manager: Optional[GoogleAuthManager] = None,
        folder_id: Optional[str] = None,
        timeout: float = 30.0
    ):
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.folder_id = folder_id
        self.timeout = timeout

    @property
    def is_simulation_mode(self) -> bool:
        return not (self.auth_manager and self.auth_manager.is_configured)

    def upload_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        folder_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        로컬 파일을 Google Drive에 업로드하고 webViewLink 반환.
        Service Account 미설정 시 mock URL 반환.
        """
        file_name = name or os.path.basename(file_path)
        target_folder = folder_id or self.folder_id

        if not mime_type:
            if file_name.endswith(".mp4"):
                mime_type = "video/mp4"
            elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
                mime_type = "image/jpeg"
            else:
                mime_type = "application/octet-stream"

        if self.is_simulation_mode:
            mock_id = f"mock_drive_{abs(hash(file_name))}"
            mock_link = f"https://drive.google.com/file/d/{mock_id}/view?usp=sharing"
            logger.info(
                f"GoogleDriveClient [Simulation]: Uploaded {file_name} -> {mock_link} (folder: {target_folder})"
            )
            return {
                "status": "success",
                "mode": "simulation",
                "file_id": mock_id,
                "file_name": file_name,
                "folder_id": target_folder,
                "web_view_link": mock_link,
                "drive_url": mock_link
            }

        # Real Google Drive API v3 Multipart Upload
        token = self.auth_manager.get_access_token()
        if not token:
            logger.warning("GoogleDriveClient: Failed to obtain valid access token. Falling back to simulation.")
            mock_id = f"mock_drive_{abs(hash(file_name))}"
            mock_link = f"https://drive.google.com/file/d/{mock_id}/view?usp=sharing"
            return {
                "status": "success",
                "mode": "simulation_fallback",
                "file_id": mock_id,
                "file_name": file_name,
                "folder_id": target_folder,
                "web_view_link": mock_link,
                "drive_url": mock_link
            }

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file not found for Drive upload: {file_path}")

        try:
            metadata: Dict[str, Any] = {"name": file_name}
            if target_folder:
                metadata["parents"] = [target_folder]

            with open(file_path, "rb") as f:
                file_content = f.read()

            files = {
                "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (file_name, file_content, mime_type)
            }

            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    f"{DRIVE_UPLOAD_URL}&fields=id,name,webViewLink,webContentLink",
                    headers=headers,
                    files=files
                )
                if res.status_code in (200, 201):
                    data = res.json()
                    file_id = data.get("id")
                    web_link = data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
                    logger.info(f"GoogleDriveClient: Successfully uploaded {file_name} (ID: {file_id})")
                    return {
                        "status": "success",
                        "mode": "real",
                        "file_id": file_id,
                        "file_name": file_name,
                        "folder_id": target_folder,
                        "web_view_link": web_link,
                        "drive_url": web_link
                    }
                else:
                    logger.error(f"GoogleDriveClient: Upload failed with status {res.status_code}: {res.text}")
                    return {
                        "status": "error",
                        "mode": "real",
                        "status_code": res.status_code,
                        "detail": res.text
                    }
        except Exception as e:
            logger.error(f"GoogleDriveClient: Exception uploading file to Drive: {e}")
            return {
                "status": "error",
                "mode": "real",
                "error": str(e)
            }
