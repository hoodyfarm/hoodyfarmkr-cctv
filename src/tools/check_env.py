import sys
import os
import socket
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.services.onvif_service import ONVIFCameraService
from src.services.oci_service import OCIDataPipelineService
from src.services.gemini_service import GeminiDatasetPipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("env_checker")

def check_cctv_connection():
    print("\n--- 1. CCTV (ONVIF/RTSP) 네트워크 연동 점검 ---")
    print(f"ONVIF Host: {settings.ONVIF_HOST}:{settings.ONVIF_PORT}")
    print(f"RTSP URL:   {settings.RTSP_STREAM_URL}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    result = sock.connect_ex((settings.ONVIF_HOST, settings.ONVIF_PORT))
    sock.close()

    if result == 0:
        print(f"✅ ONVIF 포트 ({settings.ONVIF_PORT}) 통신 성공!")
    else:
        print(f"⚠️ ONVIF 포트 ({settings.ONVIF_PORT}) 연결 실패. CCTV IP 주소 및 포트를 확인하세요.")

    onvif_service = ONVIFCameraService(
        host=settings.ONVIF_HOST,
        port=settings.ONVIF_PORT,
        user=settings.ONVIF_USER,
        pass_word=settings.ONVIF_PASSWORD
    )
    if onvif_service.connect():
        print("✅ ONVIF 프로토콜 바인딩 성공!")
        profiles = onvif_service.get_profiles()
        print(f"   감지된 미디어 프로필 수: {len(profiles)}")
    else:
        print("⚠️ ONVIF 바인딩 실패. 계정 정보(ID/비밀번호)를 확인하세요.")

def check_oci_connection():
    print("\n--- 2. Oracle Cloud (OCI) 연동 점검 ---")
    expanded_path = os.path.expanduser(settings.OCI_CONFIG_FILE)
    print(f"OCI Config File: {expanded_path}")

    if os.path.exists(expanded_path):
        print(f"✅ OCI 설정 파일 존재함: {expanded_path}")
        oci_service = OCIDataPipelineService(
            config_file=settings.OCI_CONFIG_FILE,
            profile=settings.OCI_PROFILE,
            raw_bucket=settings.OCI_BUCKET_RAW_VIDEOS,
            refined_bucket=settings.OCI_BUCKET_REFINED_FRAMES
        )
        if oci_service.client and oci_service.namespace:
            print(f"✅ OCI SDK 클라이언트 바인딩 성공! (Namespace: {oci_service.namespace})")
        else:
            print("⚠️ OCI Config 파일은 있으나 클라이언트 초기화에 실패했습니다. (API Key/Fingerprint 확인)")
    else:
        print(f"ℹ️ OCI Config 파일이 없습니다. ({expanded_path})")
        print("   -> 현재 시뮬레이션 업로드 모드로 동작 중입니다.")

def check_gemini_connection():
    print("\n--- 3. Gemini AI API 연동 점검 ---")
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here":
        print(f"✅ GEMINI_API_KEY 설정되어 있음 (Model: {settings.GEMINI_MODEL})")
        pipeline = GeminiDatasetPipeline(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
        res = pipeline.analyze_frame_with_gemini(b"dummy_test_bytes", prompt="Hello Gemini, test connection.")
        if res.get("status") == "success":
            print("✅ Gemini API 통신 성공!")
        else:
            print(f"⚠️ Gemini API 통신 메시지: {res.get('message') or res.get('note')}")
    else:
        print("ℹ️ GEMINI_API_KEY가 설정되지 않았습니다. (시뮬레이션 모드로 동작 중)")

if __name__ == "__main__":
    print("==================================================")
    print("   hoodyfarmkr-cctv 환경 연동 자가 진단 도구")
    print("==================================================")
    check_cctv_connection()
    check_oci_connection()
    check_gemini_connection()
    print("\n==================================================")
