from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional

from src.config import settings
from src.services.gemini_service import GeminiDatasetPipeline
from src.services.stream_service import VideoStreamHandler

router = APIRouter(prefix="/api/v1/gemini", tags=["Gemini AI Multimodal & Fine-Tuning"])

class DatasetRecordRequest(BaseModel):
    oci_image_uri: str
    system_instruction: str = "You are an AI cattle health monitor."
    user_prompt: str = "Analyze cattle condition from CCTV frame."
    model_response: str = "Cattle standing normally, no signs of distress."

class DirectAnalyzeRequest(BaseModel):
    prompt: Optional[str] = "Analyze cattle behavior and health from CCTV frame."

@router.post("/dataset-record")
def create_dataset_record(payload: DatasetRecordRequest) -> Dict[str, Any]:
    """
    Generate JSONL dataset record formatted for Gemini Multimodal fine-tuning.
    """
    pipeline = GeminiDatasetPipeline(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
    jsonl_line = pipeline.generate_fine_tuning_jsonl_entry(
        oci_image_uri=payload.oci_image_uri,
        system_instruction=payload.system_instruction,
        user_prompt=payload.user_prompt,
        model_response=payload.model_response
    )
    return {
        "status": "success",
        "jsonl_record": jsonl_line
    }

@router.post("/analyze-current-frame")
def analyze_current_frame(payload: DirectAnalyzeRequest) -> Dict[str, Any]:
    """
    Capture current CCTV frame and perform immediate Gemini Multimodal AI vision analysis.
    """
    stream_handler = VideoStreamHandler(settings.RTSP_STREAM_URL)
    pipeline = GeminiDatasetPipeline(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)

    import cv2
    import numpy as np
    frame = stream_handler.capture_single_frame()
    if frame is None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    _, buffer = cv2.imencode('.jpg', frame)
    analysis_result = pipeline.analyze_frame_with_gemini(buffer.tobytes(), prompt=payload.prompt)
    return {
        "status": "completed",
        "result": analysis_result
    }
