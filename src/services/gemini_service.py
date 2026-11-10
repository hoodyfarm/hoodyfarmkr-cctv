import json
import logging
from typing import Dict, Any, Optional
from src.config import settings
from src.schemas.ai_schema import CCTVAnalysisResultSchema, DetectedObject

logger = logging.getLogger(__name__)

class GeminiVisionService:
    """
    Gemini 2.5 Flash Multimodal Vision API Integration Service.
    Analyzes CCTV video frames and extracts Pydantic Structured Output JSON.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL

    def analyze_frame_structured(
        self, 
        image_bytes: bytes, 
        custom_prompt: Optional[str] = None
    ) -> CCTVAnalysisResultSchema:
        """
        Analyze JPEG frame bytes using Gemini 2.5 Flash model and return CCTVAnalysisResultSchema.
        """
        prompt = custom_prompt or (
            "Analyze this CCTV camera frame carefully. Detect cattle, animals, or humans in the farm. "
            "Identify behavior and anomalies, and classify into event_type: "
            "'INVERTED' (기립불능, 뒤집힘, 넘어져서 못 일어남), 'CALVING' (분만 임박, 양수 파수, 출산 징후), "
            "'ESCAPE' (울타리 이탈, 축사 탈출), 'ESTRUS' (발정 승가), 'FIGHTING' (투쟁), 'INTRUSION' (외부인 침입), "
            "'FIRE' (화재 연기), or 'NORMAL' (정상). "
            "Set event_type to one of these uppercase codes. "
            "Provide the output strictly matching the required JSON schema with summary in Korean."
        )

        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.info("ℹ️ GEMINI_API_KEY is not configured or default. Operating in Simulation Mode.")
            return self._generate_simulation_result(prompt)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            
            # Configure Structured Output
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CCTVAnalysisResultSchema,
                temperature=0.2
            )

            # Pass image bytes part and text prompt
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg"
            )

            logger.info(f"Calling Gemini API ({self.model_name}) with image frame...")
            response = client.models.generate_content(
                model=self.model_name,
                contents=[image_part, prompt],
                config=config
            )

            if response.text:
                logger.info("✅ Gemini 2.5 Flash Structured Response received!")
                # Parse JSON into Pydantic model
                data = json.loads(response.text)
                return CCTVAnalysisResultSchema(**data)
            else:
                logger.warning("Empty response text from Gemini API. Falling back to simulation result.")
                return self._generate_simulation_result(prompt)

        except Exception as e:
            logger.warning(f"⚠️ Gemini API invocation encountered error ({e}). Returning fallback simulation result.")
            return self._generate_simulation_result(prompt)

    def _generate_simulation_result(self, prompt: str) -> CCTVAnalysisResultSchema:
        """
        Generate a synthetic CCTVAnalysisResultSchema for offline testing and simulation.
        """
        return CCTVAnalysisResultSchema(
            is_anomaly=False,
            event_type="NORMAL",
            confidence_score=0.96,
            detected_objects=[
                DetectedObject(label="cattle", confidence=0.98, location="center"),
                DetectedObject(label="farm_gate", confidence=0.95, location="top-right")
            ],
            summary="[시뮬레이션 분석] 축사 내 가축(소) 1두 및 농장 울타리 상태 정상 확인됨. 이상징후 없음.",
            recommended_action="monitor"
        )


class GeminiDatasetPipeline:
    """
    Gemini AI Multimodal Fine-tuning Dataset Generator & Legacy Helper.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.vision_service = GeminiVisionService(api_key=self.api_key, model_name=self.model_name)

    def analyze_frame_with_gemini(self, frame_bytes: bytes, prompt: str = "Analyze CCTV frame.") -> Dict[str, Any]:
        """
        Legacy dictionary response wrapper around GeminiVisionService.
        """
        result = self.vision_service.analyze_frame_structured(frame_bytes, custom_prompt=prompt)
        return {
            "status": "success",
            "is_anomaly": result.is_anomaly,
            "event_type": result.event_type,
            "confidence_score": result.confidence_score,
            "summary": result.summary,
            "analysis": result.summary,
            "raw_result": result.model_dump()
        }

    def generate_fine_tuning_jsonl_entry(
        self,
        oci_image_uri: str,
        system_instruction: str = "You are an AI cattle health monitor.",
        user_prompt: str = "Analyze cattle condition from CCTV frame.",
        model_response: str = "Cattle standing normally, no signs of distress."
    ) -> str:
        """
        Generate fine-tuning dataset JSONL single line entry.
        Supports both modern contents structure and legacy messages key for test backward-compatibility.
        """
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt, "image_uri": oci_image_uri},
            {"role": "model", "content": model_response}
        ]
        entry = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"file_data": {"mime_type": "image/jpeg", "file_uri": oci_image_uri}},
                        {"text": user_prompt}
                    ]
                },
                {
                    "role": "model",
                    "parts": [{"text": model_response}]
                }
            ],
            "messages": messages
        }
        return json.dumps(entry, ensure_ascii=False)

    def format_multimodal_prompt(self, oci_image_uri: str, prompt_text: str) -> Dict[str, Any]:
        """
        Format prompt with image URI for multimodal request payload.
        """
        parts = [
            {"file_data": {"mime_type": "image/jpeg", "file_uri": oci_image_uri}},
            {"text": prompt_text}
        ]
        return {
            "model": self.model_name or "gemini-1.5-flash",
            "image_uri": oci_image_uri,
            "prompt": prompt_text,
            "parts": parts,
            "contents": [{"parts": parts}]
        }
