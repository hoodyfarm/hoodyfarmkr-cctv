import cv2
import logging
import numpy as np
from typing import Generator, Optional, Tuple

logger = logging.getLogger(__name__)

class VideoStreamHandler:
    """
    RTSP / CCTV Video Stream Handler using OpenCV.
    Captures live stream frames, supports MJPEG generator and keyframe extraction.
    """
    def __init__(self, stream_url: str):
        self.stream_url = stream_url

    def generate_mjpeg_frames(self) -> Generator[bytes, None, None]:
        """
        Generate MJPEG byte stream for HTTP live streaming endpoint.
        """
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            # If camera cannot be opened, generate fallback placeholder frame
            yield self._generate_fallback_frame("CCTV Stream Offline")
            return

        try:
            while True:
                success, frame = cap.read()
                if not success:
                    break
                
                # Encode frame to JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        finally:
            cap.release()

    def capture_single_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from the stream for keyframe sampling / motion detection.
        """
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            logger.warning(f"Could not open stream at {self.stream_url}")
            return None
        
        success, frame = cap.read()
        cap.release()
        return frame if success else None

    def _generate_fallback_frame(self, message: str) -> bytes:
        """
        Create a dummy black image with error text for fallback streaming.
        """
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, message, (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        _, buffer = cv2.imencode('.jpg', img)
        return (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
