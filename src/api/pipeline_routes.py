from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import datetime

from src.config import settings
from src.services.orchestrator import pipeline_orchestrator

router = APIRouter(prefix="/api/v1/pipeline", tags=["OCI Data Pipeline"])

class PipelineTriggerRequest(BaseModel):
    camera_id: str = "cam_01"
    force_run: bool = False
    note: Optional[str] = "Manual pipeline trigger"

@router.post("/trigger")
async def trigger_pipeline_cycle(payload: Optional[PipelineTriggerRequest] = None) -> Dict[str, Any]:
    """
    Trigger end-to-end pipeline cycle:
    [RTSP Frame Capture -> Motion Check -> Gemini 2.5 AI -> PostgreSQL Log -> OCI Upload -> Webhook Alert]
    """
    try:
        result = await pipeline_orchestrator.run_pipeline_cycle()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@router.get("/status")
def get_pipeline_status() -> Dict[str, Any]:
    """
    Get pipeline status and total processed frames.
    """
    return {
        "status": "active",
        "app_name": settings.APP_NAME,
        "onvif_host": settings.ONVIF_HOST,
        "gemini_model": settings.GEMINI_MODEL,
        "postgres_host": settings.POSTGRES_HOST,
        "total_processed": pipeline_orchestrator._total_processed
    }
