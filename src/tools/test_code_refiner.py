import sys
import os
import logging

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.services.ai_code_refiner import AICodeRefinerService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 60)
    print("🤖 [hoodyfarmkr-cctv] AI 자가 진단 및 자동 코드 개선 CLI (Step 6)")
    print("=" * 60)

    # Synthetic traceback for testing self-healing engine
    sample_traceback = (
        "Traceback (most recent call last):\n"
        "  File 'src/services/stream_service.py', line 45, in get_frame\n"
        "    ret, frame = self.cap.read()\n"
        "TimeoutError: RTSP connection stream buffer timed out after 5000ms\n"
    )

    sample_context_code = (
        "class StreamService:\n"
        "    def get_frame(self):\n"
        "        # Synchronous blocking call\n"
        "        ret, frame = self.cap.read()\n"
        "        return frame\n"
    )

    print("\n🔍 [1/2] 에러 트레이스백 분석 요청...")
    refiner = AICodeRefinerService()
    result = refiner.analyze_error_and_refine(sample_traceback, sample_context_code)

    print("\n✅ [2/2] Gemini 2.5 Flash 자가 진단 및 코드 개선 결과:")
    print("-" * 60)
    print(f"📌 요약: {result.error_summary}")
    print(f"🔬 기술적 원인 (RCA): {result.root_cause}")
    print(f"💡 해결 전략: {result.proposed_fix}")
    print(f"🛡️ 예방 대책: {result.prevention_strategy}")
    print("-" * 60)
    print("💻 추천 개선 코드 스니펫:")
    print(result.refactored_code_snippet)
    print("=" * 60)
    print("🎉 AI 자가 진단 CLI 자가 테스트가 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    main()
