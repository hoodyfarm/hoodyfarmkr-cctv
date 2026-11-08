import os
import time
import logging
import cv2
import numpy as np
from typing import List, Optional

logger = logging.getLogger(__name__)

class VideoEncoder:
    """
    OpenCV 기반 고성능 MP4 비디오 클립 인코더
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def encode_clip(
        self,
        frames: List[np.ndarray],
        tag: str = "event",
        fps: float = 5.0
    ) -> Optional[str]:
        """
        프레임 시퀀스를 .mp4 영상 파일로 인코딩하여 저장하고 파일 경로 반환
        """
        if not frames:
            logger.warning("VideoEncoder: No frames provided to encode.")
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"clip_{tag}_{timestamp}_{int(time.time() * 1000) % 1000}.mp4"
        filepath = os.path.join(self.output_dir, filename)

        height, width = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filepath, fourcc, float(fps), (width, height))

        if not writer.isOpened():
            logger.error(f"VideoEncoder: Failed to open VideoWriter for {filepath}")
            return None

        try:
            for frame in frames:
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        except Exception as e:
            logger.error(f"VideoEncoder: Error encoding frames: {e}")
            return None
        finally:
            writer.release()

        logger.info(f"VideoEncoder: ✅ Clip created ({len(frames)} frames @ {fps} FPS) -> {filepath}")
        return filepath
