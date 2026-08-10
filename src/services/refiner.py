import cv2
import datetime
import numpy as np
from typing import Dict, Any, Tuple, Optional

class VideoDataRefiner:
    """
    Video Data Refiner and Preprocessor.
    Parses raw CCTV frames/clips, resizes, crops, extracts keyframes,
    and structures metadata for Gemini AI dataset generation.
    """
    def __init__(self, target_width: int = 1280, target_height: int = 720):
        self.target_width = target_width
        self.target_height = target_height

    def refine_frame(self, frame: np.ndarray) -> Tuple[bytes, Dict[str, Any]]:
        """
        Resize frame, encode to JPEG, and generate structured metadata.
        """
        resized = cv2.resize(frame, (self.target_width, self.target_height))
        ret, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
        
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        metadata = {
            "timestamp": timestamp,
            "width": self.target_width,
            "height": self.target_height,
            "format": "jpeg",
            "size_bytes": len(buffer)
        }
        return buffer.tobytes(), metadata

    def detect_motion(self, prev_frame: Optional[np.ndarray], current_frame: np.ndarray, threshold: float = 10000.0) -> bool:
        """
        Simple motion detection based on absolute frame difference.
        """
        if prev_frame is None:
            return True
        
        gray1 = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray1, gray2)
        score = np.sum(diff)
        return float(score) > threshold
