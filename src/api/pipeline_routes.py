import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import datetime

from src.config import settings
from src.services.worker_manager import worker_manager

router = APIRouter(prefix="/api/v1/pipeline", tags=["OCI Data Pipeline"])
# Media links are opened from FMS/mobile browsers (no custom headers): separate unauthenticated router
media_router = APIRouter(prefix="/api/v1/pipeline", tags=["Media View"])


class PipelineTriggerRequest(BaseModel):
    camera_id: str = "cam_01"
    force_run: bool = False
    note: Optional[str] = "Manual pipeline trigger"


def _run_trigger(camera_id: Optional[str] = None) -> Dict[str, Any]:
    if camera_id is not None:
        try:
            result = worker_manager.trigger_once(camera_id=camera_id)
        except TypeError:
            result = worker_manager.trigger_once()
    else:
        result = worker_manager.trigger_once()
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="No frame available from ingestion worker (camera not connected)",
        )
    return result


@router.post("/capture-and-upload", deprecated=True)
def capture_and_upload_legacy(payload: Optional[PipelineTriggerRequest] = None) -> Dict[str, Any]:
    """Deprecated alias of /trigger (kept for backward compatibility)."""
    cam_id = payload.camera_id if payload else None
    result = _run_trigger(camera_id=cam_id)
    return {
        "status": "success",
        "oci_upload_result": {"status": "success", "oci_url": None},
        "cycle_result": result,
    }


@router.post("/trigger")
def trigger_pipeline_cycle(payload: Optional[PipelineTriggerRequest] = None) -> Dict[str, Any]:
    """Process the latest buffered frame through the unified worker pipeline (YOLO -> Gemini -> EventWorker)."""
    cam_id = payload.camera_id if payload else None
    return _run_trigger(camera_id=cam_id)


@router.get("/status")
def get_pipeline_status() -> Dict[str, Any]:
    """
    Get pipeline status, multi-camera telemetry, and webhook outbox state.
    """
    telemetry = worker_manager.get_telemetry()
    return {
        "status": "active",
        "app_name": settings.APP_NAME,
        "gemini_model": settings.GEMINI_MODEL,
        "farm_id": settings.FARM_ID,
        "workers": telemetry,
    }


@router.get("/outbox")
def get_outbox_status() -> Dict[str, Any]:
    """
    Inspect persistent webhook outbox and DLQ counts.
    """
    stats = worker_manager.outbox.get_stats() if worker_manager.outbox else {"pending": 0, "delivered": 0, "dlq": 0}
    return {"status": "ok", "farm_id": settings.FARM_ID, "outbox": stats}


@router.post("/outbox/retry")
def retry_outbox_now(include_dlq: bool = True) -> Dict[str, Any]:
    """
    Requeue DLQ events (optional) and immediately flush due pending webhook events.
    """
    requeued = 0
    if include_dlq and worker_manager.outbox is not None:
        requeued = worker_manager.outbox.requeue_dlq()
    flush_stats = worker_manager.event_worker.flush_outbox_once()
    return {
        "status": "ok",
        "requeued_from_dlq": requeued,
        "flush_result": flush_stats,
        "outbox": worker_manager.outbox.get_stats() if worker_manager.outbox else {},
    }


@router.get("/captures")
def list_captured_files(limit: int = 20) -> Dict[str, Any]:
    """
    List recent captured frames (.jpg) and video clips (.mp4) on local disk.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    events_dir = os.path.join(base_dir, "captures", "events")
    spool_dir = os.path.join(base_dir, "captures", "spool")
    clips_dir = os.path.join(base_dir, "captures", "clips")
    frames_dir = os.path.join(base_dir, "captures", "frames")

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
                    "modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        files.sort(key=lambda x: x["modified_at"], reverse=True)
        return files[:limit]

    recent_events = scan_dir(events_dir, ".jpg")
    recent_spool = scan_dir(spool_dir, ".jpg")
    recent_clips = scan_dir(clips_dir, ".mp4")
    recent_legacy = scan_dir(frames_dir, ".jpg")

    return {
        "status": "success",
        "total_events_found": len(recent_events),
        "total_spool_found": len(recent_spool),
        "total_clips_found": len(recent_clips),
        "events": recent_events,
        "spool": recent_spool,
        "clips": recent_clips,
        "legacy_frames": recent_legacy,
    }


@media_router.get("/captures/view/{folder}/{filename}")
def view_captured_file(folder: str, filename: str):
    """
    Directly view or download captured frame (.jpg) or clip (.mp4) on mobile browser.
    """
    if folder not in ["events", "spool", "frames", "clips"]:
        raise HTTPException(status_code=400, detail="Invalid folder type. Use 'frames' or 'clips'.")

    if filename != os.path.basename(filename) or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, "captures", folder, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "image/jpeg" if filename.endswith(".jpg") else "video/mp4"
    return FileResponse(file_path, media_type=media_type)
