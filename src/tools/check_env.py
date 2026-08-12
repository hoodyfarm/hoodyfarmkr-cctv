import sys
import os
import socket
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("env_checker")

def check_env_configuration():
    print("\n--- 1. 프로젝트 환경 변수 (.env) 설정 점검 ---")
    print(f"App Name:      {settings.APP_NAME}")
    print(f"Environment:   {settings.ENVIRONMENT}")
    print(f"Port:          {settings.PORT}")
    print(f"Log Level:     {settings.LOG_LEVEL}")
    
    print("\n--- 2. CCTV (ONVIF/RTSP) 설정 점검 ---")
    print(f"ONVIF Host:    {settings.ONVIF_HOST}:{settings.ONVIF_PORT}")
    print(f"ONVIF User:    {settings.ONVIF_USER}")
    masked_pw = "*" * len(settings.ONVIF_PASSWORD) if settings.ONVIF_PASSWORD else "(Not set)"
    print(f"ONVIF Pass:    {masked_pw}")
    print(f"RTSP URL:      {settings.RTSP_STREAM_URL}")
    print(f"Sampling Sec:  {settings.FRAME_SAMPLING_INTERVAL_SEC}s")

    print("\n--- 3. PostgreSQL 데이터베이스 설정 점검 ---")
    print(f"PostgreSQL Host: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    print(f"Database Name:   {settings.POSTGRES_DB}")
    print(f"User Name:       {settings.POSTGRES_USER}")
    print(f"Async DB URL:    {settings.get_database_url}")

    print("\n--- 4. Oracle Cloud (OCI) 설정 점검 ---")
    expanded_path = os.path.expanduser(settings.OCI_CONFIG_FILE)
    print(f"OCI Config:    {expanded_path}")
    print(f"OCI Region:    {settings.OCI_REGION}")
    print(f"Raw Bucket:    {settings.OCI_BUCKET_RAW_VIDEOS}")

    print("\n--- 5. Google Gemini AI API 설정 점검 ---")
    print(f"Gemini Model:  {settings.GEMINI_MODEL}")
    masked_key = (settings.GEMINI_API_KEY[:6] + "..." + settings.GEMINI_API_KEY[-4:]) if (settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY) > 10 and settings.GEMINI_API_KEY != "your_gemini_api_key_here") else "(Not configured / Default)"
    print(f"Gemini Key:    {masked_key}")

def check_cctv_network():
    print("\n--- 6. CCTV 네트워크 연결 테스트 ---")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    result = sock.connect_ex((settings.ONVIF_HOST, settings.ONVIF_PORT))
    sock.close()

    if result == 0:
        print(f"✅ ONVIF 포트 ({settings.ONVIF_PORT}) 통신 성공!")
    else:
        print(f"ℹ️ ONVIF 포트 ({settings.ONVIF_PORT}) 연결 대기 (실제 로컬 카메라 수집 환경 실행 시 시도)")

if __name__ == "__main__":
    print("==================================================")
    print("   hoodyfarmkr-cctv [1단계] 환경 연동 자가 진단")
    print("==================================================")
    check_env_configuration()
    check_cctv_network()
    print("\n==================================================")
    print("✨ [1단계] 프로젝트 환경 설정 및 .env / config.py 점검 완료!")
    print("==================================================")
