import json
import logging
from typing import Optional
from src.config import settings
from src.schemas.ai_schema import AICodeFixSuggestionSchema

logger = logging.getLogger(__name__)

class AICodeRefinerService:
    """
    AI Code Refiner & Self-Healing Diagnostics Service.
    Uses Gemini 2.5 Flash API to analyze runtime exceptions, tracebacks, or code snippets
    and outputs structured Root Cause Analysis (RCA) and suggested refactored patches.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL

    def analyze_error_and_refine(
        self,
        traceback_text: str,
        context_code: Optional[str] = None
    ) -> AICodeFixSuggestionSchema:
        """
        Analyze a python error traceback + optional code snippet and return structured fix suggestion.
        """
        prompt = (
            "Analyze the following Python error traceback and context code from the hoodyfarmkr-cctv AI pipeline.\n"
            "Identify the root cause, propose an async/fastapi best-practice fix, and provide a clean refactored Python code snippet.\n\n"
            f"--- ERROR TRACEBACK ---\n{traceback_text}\n"
        )
        if context_code:
            prompt += f"\n--- CONTEXT CODE ---\n{context_code}\n"

        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.info("ℹ️ GEMINI_API_KEY is not configured or default. Operating in Simulation Mode.")
            return self._generate_simulation_fix(traceback_text)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AICodeFixSuggestionSchema,
                temperature=0.1
            )

            logger.info(f"Calling Gemini API ({self.model_name}) for AI Code Refinement...")
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )

            if response.text:
                logger.info("✅ Gemini Code Refiner response received!")
                data = json.loads(response.text)
                return AICodeFixSuggestionSchema(**data)
            else:
                logger.warning("Empty response from Gemini Code Refiner API. Returning simulation result.")
                return self._generate_simulation_fix(traceback_text)

        except Exception as e:
            logger.warning(f"⚠️ Gemini API invocation error ({e}). Returning fallback simulation fix.")
            return self._generate_simulation_fix(traceback_text)

    def _generate_simulation_fix(self, traceback_text: str) -> AICodeFixSuggestionSchema:
        """
        Generate a synthetic AICodeFixSuggestionSchema for offline testing and simulation mode.
        """
        return AICodeFixSuggestionSchema(
            error_summary="[시뮬레이션 진단] RTSP 프레임 캡처 또는 비동기 DB 커넥션 타임아웃 예외 감지",
            root_cause="동기식 OpenCV cv2.VideoCapture() 메서드가 비동기 FastAPI 이벤트 루프를 블로킹하여 타임아웃이 발생함.",
            proposed_fix="OpenCV 캡처 로직을 asyncio.to_thread() 또는 전용 백그라운드 Worker 스레드로 격리하여 비동기 루프 블로킹 해제.",
            refactored_code_snippet=(
                "import asyncio\n"
                "import cv2\n\n"
                "async def fetch_frame_async(cap):\n"
                "    loop = asyncio.get_running_loop()\n"
                "    ret, frame = await loop.run_in_executor(None, cap.read)\n"
                "    return ret, frame\n"
            ),
            prevention_strategy="OpenCV 수집 모듈에 asyncio executor를 적용하고 pytest-asyncio 통합 테스트 추가"
        )
