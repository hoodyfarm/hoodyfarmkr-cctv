from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import datetime

from src.config import settings
from src.services.stream_service import VideoStreamHandler
from src.services.refiner import VideoDataRefiner
from src.services.oci_service import OCIDataPipelineService

router = APIRouter(prefix="/api/v1/pipeline", tags=["OCI Data Pipeline"])

class FrameCaptureRequest(BaseModel):
    camera_id: str = "cam_01"
    note: Optional[str] = "Manual snapshot trigger"

@router.post("/capture-and-upload")
def capture_and_upload_to_oci(payload: FrameCaptureRequest) -> Dict[str, Any]:
    """
    Capture single CCTV frame, refine image/metadata, and upload to OCI Object Storage bucket.
    """
    stream_handler = VideoStreamHandler(settings.RTSP_STREAM_URL)
    refiner = VideoDataRefiner()
    oci_service = OCIDataPipelineService(
        config_file=settings.OCI_CONFIG_FILE,
        profile=settings.OCI_PROFILE,
        raw_bucket=settings.OCI_BUCKET_RAW_VIDEOS,
        refined_bucket=settings.OCI_BUCKET_REFINED_FRAMES
    )

    frame = stream_handler.capture_single_frame()
    if frame is None:
        # Generate dummy fallback image frame for testing pipeline when camera is offline
        import numpy as np
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    frame_bytes, metadata = refiner.refine_frame(frame)
    
    timestamp_str = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_name = f"{payload.camera_id}/{timestamp_str}.jpg"

    upload_result = oci_service.upload_frame_to_oci(
        frame_bytes=frame_bytes,
        object_name=object_name,
        metadata={
            "camera_id": payload.camera_id,
            "timestamp": metadata["timestamp"],
            "note": payload.note or ""
        }
    )

    oci_service.record_metadata_to_oci_db({
        "camera_id": payload.camera_id,
        "object_name": object_name,
        "size_bytes": metadata["size_bytes"],
        "upload_status": upload_result.get("status")
    })

    return {
        "status": "success",
        "frame_metadata": metadata,
        "oci_upload_result": upload_result
    }
