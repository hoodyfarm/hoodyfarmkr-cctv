import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class DetectionTarget(BaseModel):
    label: str
    confidence: float
    bbox: Optional[List[float]] = None

class DetectionEvent(BaseModel):
    """
    InferenceWorker에서 객체(소/사람 등) 감지 시 발행하는 내부 도메인 이벤트
    """
    event_id: str
    camera_id: str = "default_cctv"
    tag: str
    timestamp: float = Field(default_factory=time.time)
    detections: List[DetectionTarget]
    frame_path: str
    is_anomaly: bool = False
    ai_summary: Optional[str] = None
    pre_sec: float = 3.0
    post_sec: float = 3.0
