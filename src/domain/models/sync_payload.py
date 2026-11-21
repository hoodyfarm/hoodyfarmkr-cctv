from typing import List, Optional
from pydantic import BaseModel, Field


class CameraSyncItem(BaseModel):
    """FMS에서 전달하는 개별 카메라 동기화 정보"""
    camera_id: str = Field(..., description="카메라 고유 식별자 (예: CAM_BARN_01)")
    camera_name: str = Field(..., description="카메라 표시 이름 (예: 1번사 송아지방)")
    zone: Optional[str] = Field("pen_01", description="배치 구역/돈방/우방 번호")
    local_ip: str = Field(..., description="카메라 로컬 IP (예: 192.168.0.217)")
    onvif_port: int = Field(8899, description="ONVIF 포트")
    username: str = Field("admin", description="ONVIF/RTSP 계정")
    password: str = Field("", description="ONVIF/RTSP 비밀번호")
    stream_type: int = Field(1, description="스트림 모드: 1(AI 서브스트림 640p, 권장), 0(고화질 메인스트림 2K/4K)")
    rtsp_url: Optional[str] = Field(None, description="명시적 RTSP 주소 (생략 시 local_ip와 계정으로 자동 생성)")
    fps: float = Field(5.0, description="목표 FPS")
    ring_buffer_sec: float = Field(10.0, description="이벤트 전후 캡처 링 버퍼 초")
    enabled: bool = Field(True, description="활성화 여부")

    def build_rtsp_url(self) -> str:
        """rtsp_url이 비어있으면 로컬 IP와 계정 정보, 스트림 모드로 표준 RTSP URL을 자동 조합합니다."""
        if self.rtsp_url and self.rtsp_url.strip():
            return self.rtsp_url.strip()
        user_part = f"{self.username}:{self.password}@" if self.username else ""
        return f"rtsp://{user_part}{self.local_ip}:554/streamtype={self.stream_type}"


class FarmSyncPayload(BaseModel):
    """FMS에서 전송하는 축사 전체 카메라 동기화 페이로드"""
    farm_id: Optional[str] = Field("hoodyfarm", description="농장 고유 식별자")
    farm_name: Optional[str] = Field("후디팜 한우 스마트축사", description="농장 명칭")
    cameras: List[CameraSyncItem] = Field(..., description="동기화할 카메라 목록")
