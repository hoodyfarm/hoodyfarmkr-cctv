import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GeminiDatasetPipeline:
    """
    Gemini AI Multimodal Integration & Fine-tuning Dataset Generator.
    Formats refined CCTV images/video clips & OCI metadata into Gemini API payloads
    and exports JSONL training datasets.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def format_multimodal_prompt(self, oci_image_url: str, prompt_text: str) -> Dict[str, Any]:
        """
        Format Gemini Multimodal API Request Payload with OCI Image reference.
        """
        return {
            "model": self.model_name,
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt_text},
                        {"file_data": {"mime_type": "image/jpeg", "file_uri": oci_image_url}}
                    ]
                }
            ]
        }

    def generate_fine_tuning_jsonl_entry(
        self,
        oci_image_uri: str,
        system_instruction: str,
        user_prompt: str,
        model_response: str
    ) -> str:
        """
        Create a single JSONL record format for Gemini Multimodal Fine-Tuning dataset.
        """
        data = {
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": oci_image_uri}},
                        {"type": "text", "text": user_prompt}
                    ]
                },
                {
                    "role": "assistant",
                    "content": model_response
                }
            ]
        }
        return json.dumps(data, ensure_ascii=False)

    def analyze_frame_with_gemini(self, frame_bytes: bytes, prompt: str = "Analyze CCTV frame for cattle health and behavior.") -> Dict[str, Any]:
        """
        Call Gemini Multimodal API directly with frame bytes.
        """
        if not self.api_key:
            return {
                "status": "mock",
                "analysis": "Mock analysis: Cattle detected in frame. Status normal.",
                "note": "GEMINI_API_KEY is not configured. Returning simulated result."
            }

        try:
            # Google GenAI SDK integration
            from google import genai
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=[prompt, frame_bytes]
            )
            return {
                "status": "success",
                "analysis": response.text
            }
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return {"status": "error", "message": str(e)}
