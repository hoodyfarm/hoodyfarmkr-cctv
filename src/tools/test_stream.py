import sys
import os
import time
import logging
import cv2

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.services.onvif_service import ONVIFCameraService
from src.services.stream_service import VideoStreamHandler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_stream")

def run_stream_diagnostics():
    print("==================================================")
    print(" 📹 hoodyfarmkr-cctv [2단계] RTSP/ONVIF 수집 및 영상 진단")
    print("==================================================")

    # 1. ONVIF Stream URI fetch
    print("\n[1/4] ONVIF 카메라 접속 및 RTSP URI 획득 시도...")
    onvif_service = ONVIFCameraService()
    stream_url = onvif_service.get_stream_url()
    device_info = onvif_service.get_device_information()
    
    print(f" -> ONVIF Host:       {device_info['host']}:{device_info['port']}")
    print(f" -> Device Model:     {device_info['model']} ({device_info['manufacturer']})")
    print(f" -> Target RTSP URL:  {stream_url}")

    # 2. RTSP Stream Handler Initialization & Frame Capture
    print("\n[2/4] OpenCV RTSP 프레임 샘플링 테스트 (Auto-Reconnect 포함)...")
    handler = VideoStreamHandler(stream_url=stream_url)
    
    frame_1, is_synthetic_1 = handler.capture_frame_with_retry(max_retries=2, delay_sec=0.5)
    if frame_1 is not None:
        h, w, c = frame_1.shape
        mode_str = "시뮬레이션(Synthetic) 프레임" if is_synthetic_1 else "실제 CCTV 프레임"
        print(f" ✅ 첫 번째 프레임 수집 성공! [{mode_str}] (해상도: {w}x{h}, 채널: {c})")
    else:
        print(" ❌ 프레임 수집 실패")
        return

    # 3. Motion Detection & Second Frame Capture
    print("\n[3/4] 연속 2개 프레임 수집 및 모션 델타(변화율) 계산...")
    time.sleep(1.0)
    frame_2, is_synthetic_2 = handler.capture_frame_with_retry(max_retries=2, delay_sec=0.5)
    
    if frame_2 is not None:
        motion_score = handler.calculate_motion_delta(frame_1, frame_2)
        threshold = settings.MOTION_DETECTION_THRESHOLD
        print(f" -> 계산된 모션 Score: {motion_score:.2f} (임계치: {threshold})")
        if motion_score > 0:
            print(" ✅ 프레임 간 변화(모션) 감지 프로세서 정상 작동 확인!")
        else:
            print(" ℹ️ 프레임 변화 없음 (정적 영상)")

    # 4. JPEG Encoding & Output File Save Test
    print("\n[4/4] JPEG 엔코딩 및 샘플 이미지 저장 테스트...")
    jpeg_bytes = handler.frame_to_jpeg_bytes(frame_1)
    if jpeg_bytes:
        output_filename = "temp_sample_frame.jpg"
        with open(output_filename, "wb") as f:
            f.write(jpeg_bytes)
        size_kb = len(jpeg_bytes) / 1024.0
        print(f" ✅ JPEG 이미지 생성 성공! 파일: {output_filename} ({size_kb:.2f} KB)")
    else:
        print(" ❌ JPEG 엔코딩 실패")

    print("\n==================================================")
    print("✨ [2단계] RTSP 프레임 수집 및 영상 테스트 모듈 진단 완료!")
    print("==================================================")

if __name__ == "__main__":
    run_stream_diagnostics()
