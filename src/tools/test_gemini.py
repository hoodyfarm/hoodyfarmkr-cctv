import sys
import os
import logging
import json

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.services.stream_service import VideoStreamHandler
from src.services.gemini_service import GeminiVisionService
from src.schemas.ai_schema import CCTVAnalysisResultSchema

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_gemini")

def run_gemini_diagnostics():
    print("==================================================")
    print(" 🤖 hoodyfarmkr-cctv [4단계] Gemini 2.5 Flash API & Structured Output 진단")
    print("==================================================")

    # 1. Gemini 설정 점검
    print("\n[1/3] Gemini API 모델 및 Key 상태 확인...")
    print(f" -> Gemini Model: {settings.GEMINI_MODEL}")
    has_key = settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here"
    key_status = "설정됨 (실제 API 호출 진행)" if has_key else "미설정/기본값 (시뮬레이션 모드 작동)"
    print(f" -> API Key 상태: {key_status}")

    # 2. 테스트 프레임 준비
    print("\n[2/3] 분석 대상 영상 프레임 준비 중...")
    handler = VideoStreamHandler()
    sample_img = handler.generate_synthetic_test_frame("Gemini 2.5 Flash Test CCTV Frame")
    jpeg_bytes = handler.frame_to_jpeg_bytes(sample_img)
    if not jpeg_bytes:
        print(" ❌ 프레임 JPEG 변환 실패")
        return
    print(f" ✅ 테스트 프레임 준비 완료 ({len(jpeg_bytes) / 1024.0:.2f} KB)")

    # 3. Gemini Vision API 호출 & Structured Output 검증
    print("\n[3/3] GeminiVisionService.analyze_frame_structured() 실행...")
    service = GeminiVisionService()
    result = service.analyze_frame_structured(jpeg_bytes)

    print("\n📊 [Gemini 2.5 Flash Structured Output 분석 결과]")
    print(f" 🟢 이상 징후 감지 여부 (is_anomaly):      {result.is_anomaly}")
    print(f" 🏷️ 이벤트 유형 (event_type):               {result.event_type}")
    print(f" 🎯 신뢰도 점수 (confidence_score):        {result.confidence_score:.2f}")
    print(f" 🔍 권장 대응 조치 (recommended_action):    {result.recommended_action}")
    print(f" 📝 한글 요약 (summary):                    {result.summary}")
    print(" 📦 감지된 객체 목록 (detected_objects):")
    for obj in result.detected_objects:
        print(f"    - {obj.label} (신뢰도: {obj.confidence:.2f}, 위치: {obj.location or 'N/A'})")

    print("\n📄 [Pydantic JSON Dump Output]")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

    print("\n==================================================")
    print("✨ [4단계] Gemini 2.5 Flash API & Structured Output 진단 완료!")
    print("==================================================")

if __name__ == "__main__":
    run_gemini_diagnostics()
