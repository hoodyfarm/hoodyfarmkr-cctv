import time
import threading
import queue
import collections
import logging
import cv2
import numpy as np
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

class IngestionWorker:
    """
    초경량 RTSP 프레임 수집 전용 Worker (생산자).
    - 메인 스트림에서 설정된 FPS(기본 1~2 FPS)로만 저주파 샘플링
    - 최신 프레임 1장만 보관하는 고정 큐(maxsize=1)로 메모리/레이턴시 0ms 유지
    - 카메라 네트워크 끊김 시 3초 주기 자동 재연결(Watchdog)
    """

    def __init__(
        self,
        stream_url: str,
        target_fps: float = 5.0,
        max_queue_size: int = 1,
        ring_buffer_sec: float = 10.0
    ):
        self.stream_url = stream_url
        self.target_fps = target_fps
        self.interval = 1.0 / target_fps if target_fps > 0 else 0.2
        self.frame_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        
        # 3초 전후 영상 클립 생성을 위한 고정 크기 타임스탬프 링 버퍼
        self.ring_buffer_maxlen = max(int(target_fps * ring_buffer_sec), 30)
        self.ring_buffer: collections.deque = collections.deque(maxlen=self.ring_buffer_maxlen)
        self._buffer_lock = threading.Lock()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        
        # Telemetry & Metrics
        self.total_captured = 0
        self.last_capture_time = 0.0
        self.is_connected = False
        self.reconnect_count = 0

    def start(self):
        """수집 백그라운드 스레드 가동"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="IngestionWorkerThread")
        self._thread.start()
        logger.info(f"IngestionWorker started. Target FPS: {self.target_fps}, Interval: {self.interval:.2f}s")

    def stop(self):
        """수집 스레드 및 카메라 리소스 안전 해제"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_camera()
        self.is_connected = False
        logger.info("IngestionWorker stopped safely.")

    def get_latest_frame(self, timeout: float = 0.5) -> Optional[np.ndarray]:
        """소비자(추론 워커)가 가장 최신의 프레임을 논블로킹으로 꺼내가는 메서드"""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_buffered_frames_around(
        self,
        event_time: float,
        pre_sec: float = 3.0,
        post_sec: float = 3.0
    ) -> List[np.ndarray]:
        """
        이벤트 발생 시점(event_time) 기준 [event_time - pre_sec, event_time + post_sec] 범위의
        링 버퍼 내 프레임들을 시간 순서대로 복사하여 반환.
        """
        start_time = event_time - pre_sec
        end_time = event_time + post_sec
        with self._buffer_lock:
            selected = [
                frame.copy()
                for ts, frame in self.ring_buffer
                if start_time <= ts <= end_time
            ]
        return selected

    def get_recent_frames(self, count: int = 30) -> List[np.ndarray]:
        """버퍼 내 가장 최근 N개 프레임 반환"""
        with self._buffer_lock:
            items = list(self.ring_buffer)
            return [frame.copy() for _, frame in items[-count:]]

    def _connect_camera(self) -> bool:
        """OpenCV RTSP 버퍼 최소화 연결"""
        self._release_camera()
        logger.info(f"IngestionWorker: Connecting to RTSP: {self.stream_url}")
        
        # Windows DirectShow or FFMPEG with 1-frame buffer
        cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if cap.isOpened():
            self._cap = cap
            self.is_connected = True
            logger.info("IngestionWorker: ✅ RTSP stream opened successfully.")
            return True
        else:
            self._cap = None
            self.is_connected = False
            self.reconnect_count += 1
            logger.warning(f"IngestionWorker: ⚠️ Failed to open RTSP stream. Reconnect attempts: {self.reconnect_count}")
            return False

    def _release_camera(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _run_loop(self):
        """핵심 캡처 루프: 프레임을 최신으로 유지하며 저주파(1.5 FPS) 샘플링"""
        while self._running:
            if not self.is_connected or self._cap is None or not self._cap.isOpened():
                if not self._connect_camera():
                    time.sleep(3.0)  # 재연결 백오프
                    continue

            # 프레임 읽기
            ret, frame = self._cap.read()
            now = time.time()
            
            if not ret or frame is None:
                logger.warning("IngestionWorker: Frame grab returned False. Reconnecting...")
                self.is_connected = False
                self._release_camera()
                time.sleep(1.0)
                continue

            # 목표 FPS 간격 조절
            if now - self.last_capture_time >= self.interval:
                self.last_capture_time = now
                self.total_captured += 1
                
                # 링 버퍼에 타임스탬프와 함께 보관 (초당 5프레임 기준 10초 = 최대 50프레임)
                with self._buffer_lock:
                    self.ring_buffer.append((now, frame))
                
                # 큐가 꽉 찼으면 이전 프레임을 버리고 가장 최신 프레임으로 덮어씀 (Zero-Latency Ring Queue)
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
            else:
                # CPU 점유율 방어를 위한 미세 슬립 (3500X CPU 보호)
                time.sleep(0.01)

        self._release_camera()
