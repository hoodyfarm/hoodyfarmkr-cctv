"""
Pydantic Schemas package for hoodyfarmkr-cctv.
"""
from src.schemas.ai_schema import DetectedObject, CCTVAnalysisResultSchema

__all__ = [
    "DetectedObject",
    "CCTVAnalysisResultSchema",
]
