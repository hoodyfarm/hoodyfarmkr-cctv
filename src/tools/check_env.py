import sys
import os
import socket
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("env_checker")

import sys
import os
import socket
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.domain.models.farm_profile import FarmProfile

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("env_checker")

def check_env_configuration():
    print("\n--- 1. 프로젝트 환경 변수 (.env) 설정 점검 ---")
    print(f"App Name:          {settings.APP_NAME}")
    print(f"Environment:       {settings.ENVIRONMENT}")
    print(f"Port:              {settings.PORT}")
    print(f"Log Level:         {settings.LOG_LEVEL}")
    print(f"Farm ID:           {settings.FARM_ID}")
    print(f"Farm Profile Path: {settings.FARM_PROFILE_PATH or '(Auto-detect hoodyfarm.yaml)'}")

    # Check Farm Profile if present
    profile = None
    if settings.FARM_PROFILE_PATH and os.path.exists(settings.FARM_PROFILE_PATH):
        profile = FarmProfile.from_yaml(settings.FARM_PROFILE_PATH)
    elif os.path.exists("config/farms/hoodyfarm.yaml"):
        profile = FarmProfile.from_yaml("config/farms/hoodyfarm.yaml")
    else:
        profile = FarmProfile.from_settings(settings)

    if profile:
        print(f" -> Farm Profile Loaded: {profile.farm_name} ({profile.farm_id}), Cameras: {len(profile.cameras)}")
        for cam in profile.cameras:
            print(f"    * Camera [{cam.camera_id}]: {cam.name} (zone={cam.zone}) enabled={cam.enabled}")
    
    print("\n--- 2. CCTV (ONVIF/RTSP) 설정 점검 ---")
    print(f"ONVIF Host:        {settings.ONVIF_HOST}:{settings.ONVIF_PORT}")
    print(f"ONVIF User:        {settings.ONVIF_USER}")
    masked_pw = "*" * len(settings.ONVIF_PASSWORD) if settings.ONVIF_PASSWORD else "(Not set)"
    print(f"ONVIF Pass:        {masked_pw}")
    print(f"RTSP URL:          {settings.RTSP_STREAM_URL}")
    print(f"Sampling Sec:      {settings.FRAME_SAMPLING_INTERVAL_SEC}s")

    print("\n--- 3. FMS 웹훅 및 미디어 스트리밍 점검 ---")
    print(f"FMS Webhook URL:   {settings.FMS_WEBHOOK_URL or '(Not configured)'}")
    print(f"Tailscale (Active):{settings.TAILSCALE_HOST_URL or '(Not configured)'}")
    print(f"Tailscale 3500X:   {settings.TAILSCALE_HOST_3500X}")
    print(f"Tailscale 5700X3D: {settings.TAILSCALE_HOST_5700X3D}")
    print(f"Tailscale DEV:     {settings.TAILSCALE_HOST_DEV or '(미지정)'}")
    print(f"Tailscale PROD:    {settings.TAILSCALE_HOST_PROD or '(미지정)'}")

    print("\n--- 4. PostgreSQL 데이터베이스 설정 점검 ---")
    print(f"PostgreSQL Host:   {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    print(f"Database Name:     {settings.POSTGRES_DB}")
    print(f"User Name:         {settings.POSTGRES_USER}")
    print(f"Async DB URL:      {settings.get_database_url}")

    print("\n--- 5. Oracle Cloud (OCI) 설정 점검 ---")
    expanded_path = os.path.expanduser(settings.OCI_CONFIG_FILE)
    print(f"OCI Config:        {expanded_path}")
    print(f"OCI Region:        {settings.OCI_REGION}")
    print(f"Raw Bucket:        {settings.OCI_BUCKET_RAW_VIDEOS}")

    print("\n--- 6. Google Gemini AI API 설정 점검 ---")
    print(f"Gemini Model:      {settings.GEMINI_MODEL}")
    masked_key = (settings.GEMINI_API_KEY[:6] + "..." + settings.GEMINI_API_KEY[-4:]) if (settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY) > 10 and settings.GEMINI_API_KEY != "your_gemini_api_key_here") else "(Not configured / Default)"
    print(f"Gemini Key:        {masked_key}")

def check_cctv_network():
    print("\n--- 7. CCTV 네트워크 연결 테스트 ---")
    cams = [
        ("카메라 1 (CAM_BARN_01)", settings.ONVIF_HOST, settings.ONVIF_PORT),
    ]
    if settings.ONVIF_HOST_CAM02:
        cams.append(("카메라 2 (CAM_BARN_02)", settings.ONVIF_HOST_CAM02, settings.ONVIF_PORT_CAM02))

    for label, host, port in cams:
        if not host:
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"✅ {label} ONVIF 포트 ({host}:{port}) 통신 성공!")
        else:
            print(f"ℹ️ {label} ONVIF 포트 ({host}:{port}) 연결 실패 또는 대기 중")

def check_fms_network():
    print("\n--- 8. FMS 웹훅 엔드포인트 연결 테스트 ---")
    if not settings.FMS_WEBHOOK_URL:
        print("ℹ️ FMS_WEBHOOK_URL이 설정되지 않았습니다.")
        return
    import urllib.parse
    parsed = urllib.parse.urlparse(settings.FMS_WEBHOOK_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    res = sock.connect_ex((host, port))
    sock.close()
    if res == 0:
        print(f"✅ FMS 엔드포인트 ({host}:{port}) TCP 통신 연결 가능!")
    else:
        print(f"ℹ️ FMS 엔드포인트 ({host}:{port}) 현재 미기동 (Outbox 장애 격리/DLQ 모드로 자동 대응)")

if __name__ == "__main__":
    print("==================================================")
    print("   hoodyfarmkr-cctv [1단계] 환경 연동 자가 진단")
    print("==================================================")
    check_env_configuration()
    check_cctv_network()
    check_fms_network()
    print("\n==================================================")
    print("✨ [1단계] 프로젝트 환경 설정 및 네트워크 점검 완료!")
    print("==================================================")
