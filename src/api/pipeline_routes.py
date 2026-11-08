import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import datetime

from src.config import settings
from src.services.orchestrator import pipeline_orchestrator
from src.services.worker_manager import worker_manager

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
    telemetry = worker_manager.get_telemetry()
    return {
        "status": "active",
        "app_name": settings.APP_NAME,
        "onvif_host": settings.ONVIF_HOST,
        "gemini_model": settings.GEMINI_MODEL,
        "postgres_host": settings.POSTGRES_HOST,
        "total_processed": pipeline_orchestrator._total_processed,
        "workers": telemetry
    }

@router.get("/captures")
def list_captured_files(limit: int = 20) -> Dict[str, Any]:
    """
    List recent captured frames (.jpg) and video clips (.mp4) on 3500X local disk.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    frames_dir = os.path.join(base_dir, "captures", "frames")
    clips_dir = os.path.join(base_dir, "captures", "clips")

    def scan_dir(target_dir: str, ext: str):
        if not os.path.exists(target_dir):
            return []
        files = []
        for f in os.listdir(target_dir):
            if f.endswith(ext):
                path = os.path.join(target_dir, f)
                stat = os.stat(path)
                files.append({
                    "filename": f,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        files.sort(key=lambda x: x["modified_at"], reverse=True)
        return files[:limit]

    recent_frames = scan_dir(frames_dir, ".jpg")
    recent_clips = scan_dir(clips_dir, ".mp4")

    return {
        "status": "success",
        "total_frames_found": len(recent_frames),
        "total_clips_found": len(recent_clips),
        "frames": recent_frames,
        "clips": recent_clips
    }

@router.get("/captures/view/{folder}/{filename}")
def view_captured_file(folder: str, filename: str):
    """
    Directly view or download captured frame (.jpg) or clip (.mp4) on mobile browser.
    """
    if folder not in ["frames", "clips"]:
        raise HTTPException(status_code=400, detail="Invalid folder type. Use 'frames' or 'clips'.")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, "captures", folder, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    media_type = "image/jpeg" if filename.endswith(".jpg") else "video/mp4"
    return FileResponse(file_path, media_type=media_type)
