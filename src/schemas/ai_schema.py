from typing import List, Optional
from pydantic import BaseModel, Field

class DetectedObject(BaseModel):
    """Schema for individual objects detected in the CCTV frame."""
    label: str = Field(description="Object label (e.g. person, vehicle, cattle, fire, smoke, intruder)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Detection confidence score between 0.0 and 1.0")
    location: Optional[str] = Field(default=None, description="Location within the frame (e.g. top-left, center, gate)")

class CCTVAnalysisResultSchema(BaseModel):
    """Pydantic Structured Output schema for Gemini 2.5 Flash CCTV vision analysis."""
    is_anomaly: bool = Field(description="True if unusual event, intrusion, hazard, or anomaly is detected")
    event_type: str = Field(default="normal", description="Event classification: normal, intrusion, motion_alert, fire_hazard, object_detected, system_alert")
    confidence_score: float = Field(default=0.9, ge=0.0, le=1.0, description="Overall AI analysis confidence score")
    detected_objects: List[DetectedObject] = Field(default_factory=list, description="List of detected objects in the scene")
    summary: str = Field(description="Detailed Korean summary explaining what is occurring in the frame")
    recommended_action: str = Field(default="monitor", description="Recommended action: monitor, notify_operator, trigger_alarm, log_only")

class AICodeFixSuggestionSchema(BaseModel):
    """Pydantic Structured Output schema for Gemini 2.5 Flash self-healing code refiner."""
    error_summary: str = Field(description="Brief Korean summary of the identified error or bottleneck")
    root_cause: str = Field(description="Technical root cause analysis (RCA)")
    proposed_fix: str = Field(description="Detailed step-by-step resolution strategy")
    refactored_code_snippet: str = Field(description="Executable Python code snippet containing the fix or refactored logic")
    prevention_strategy: str = Field(default="Add unit test and async exception handler", description="Best practice to prevent future regression")

