import cv2
import time
import logging
import datetime
import numpy as np
from typing import Generator, Optional, Tuple, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class VideoStreamHandler:
    """
    RTSP / CCTV Video Stream Handler using OpenCV.
    Captures live stream frames, handles auto-reconnection, keyframe sampling,
    motion detection, and synthetic frame generation for testing.
    """
    def __init__(self, stream_url: Optional[str] = None):
        self.stream_url = stream_url or settings.RTSP_STREAM_URL
        self.max_reconnect_attempts = settings.MAX_RTSP_RECONNECT_ATTEMPTS

    def capture_single_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from the RTSP stream.
        Returns NumPy array (BGR frame) or None if stream is unavailable.
        """
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            logger.warning(f"Could not open RTSP stream at {self.stream_url}")
            return None

        try:
            success, frame = cap.read()
            return frame if success else None
        finally:
            cap.release()

    def capture_frame_with_retry(self, max_retries: Optional[int] = None, delay_sec: float = 1.0) -> Tuple[Optional[np.ndarray], bool]:
        """
        Capture a frame with automatic retry & reconnect logic.
        Returns (frame, is_synthetic_fallback).
        """
        retries = max_retries or self.max_reconnect_attempts

        for attempt in range(1, retries + 1):
            frame = self.capture_single_frame()
            if frame is not None:
                return frame, False
            
            logger.warning(f"RTSP frame capture failed (Attempt {attempt}/{retries}). Retrying in {delay_sec}s...")
            time.sleep(delay_sec)

        logger.warning(f"Failed to capture RTSP frame after {retries} attempts. Generating synthetic test frame for simulation.")
        return self.generate_synthetic_test_frame("RTSP Stream Offline - Simulation Frame"), True

    def calculate_motion_delta(self, prev_frame: np.ndarray, curr_frame: np.ndarray) -> float:
        """
        Calculate motion score between two consecutive frames using absolute difference.
        """
        try:
            gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            gray_curr = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            
            # Blur to reduce noise
            gray_prev = cv2.GaussianBlur(gray_prev, (21, 21), 0)
            gray_curr = cv2.GaussianBlur(gray_curr, (21, 21), 0)

            # Compute absolute difference
            frame_delta = cv2.absdiff(gray_prev, gray_curr)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

            # Motion score is count of changed non-zero pixels
            motion_score = float(np.sum(thresh > 0))
            return motion_score
        except Exception as e:
            logger.error(f"Error computing motion delta: {e}")
            return 0.0

    def frame_to_jpeg_bytes(self, frame: np.ndarray, quality: int = 90) -> Optional[bytes]:
        """
        Encode NumPy frame to JPEG byte array.
        """
        try:
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if ret:
                return buffer.tobytes()
        except Exception as e:
            logger.error(f"Failed to encode frame to JPEG: {e}")
        return None

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """
        Generate HTTP boundary-delimited MJPEG stream bytes.
        """
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            yield self._generate_fallback_mjpeg("CCTV Stream Offline")
            return

        try:
            while True:
                success, frame = cap.read()
                if not success:
                    break

                jpeg_bytes = self.frame_to_jpeg_bytes(frame)
                if jpeg_bytes:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
        finally:
            cap.release()

    def generate_synthetic_test_frame(self, label: str = "SmartLife CCTV Test Stream") -> np.ndarray:
        """
        Generate a synthetic 640x480 test image frame with timestamp and grid for testing.
        """
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Dark green/blue background
        img[:, :] = (30, 40, 25)
        
        # Grid lines
        for y in range(0, 480, 60):
            cv2.line(img, (0, y), (640, y), (50, 60, 45), 1)
        for x in range(0, 640, 80):
            cv2.line(img, (x, 0), (x, 480), (50, 60, 45), 1)

        # Header box
        cv2.rectangle(img, (20, 20), (620, 80), (70, 90, 60), -1)
        cv2.putText(img, label, (30, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Timestamp
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
        cv2.putText(img, f"Timestamp: {now_str}", (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
        cv2.putText(img, f"Stream URL: {self.stream_url[:40]}...", (30, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Simulated Object (Motion box)
        cv2.rectangle(img, (220, 240), (420, 380), (0, 200, 255), 2)
        cv2.putText(img, "Simulated Object [CCTV Test]", (230, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

        return img

    def _generate_fallback_mjpeg(self, message: str) -> bytes:
        """
        Create fallback MJPEG chunk for offline streaming.
        """
        img = self.generate_synthetic_test_frame(message)
        jpeg_bytes = self.frame_to_jpeg_bytes(img) or b""
        return (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
