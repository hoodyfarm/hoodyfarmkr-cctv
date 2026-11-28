import asyncio
import cv2
import datetime
import logging
import os
import re
import shutil
import time
from typing import Any, Dict, Generator, Optional, Tuple
import numpy as np
import yaml

from src.config import settings
from src.services.network_scanner import (
    AsyncNetworkScanner,
    HARDWARE_MASTER_REGISTRY,
    CAMERA_ID_TO_MAC,
    get_arp_table,
    normalize_mac,
)

logger = logging.getLogger(__name__)

# 카메라별 자동 힐링 지수 백오프 상태 캐시
# camera_id -> {"last_attempt": float, "failures": int, "cooldown": float}
_AUTO_HEAL_STATE: Dict[str, Dict[str, Any]] = {}
INITIAL_COOLDOWN_SEC = 10.0
MAX_COOLDOWN_SEC = 300.0


def reset_auto_heal_state(camera_id: Optional[str] = None):
    """테스트 또는 수동 리셋용 쿨다운 상태 초기화."""
    global _AUTO_HEAL_STATE
    if camera_id:
        _AUTO_HEAL_STATE.pop(camera_id, None)
    else:
        _AUTO_HEAL_STATE.clear()


def auto_heal_camera_ip(
    camera_id: str,
    yaml_path: Optional[str] = None,
    scanner: Optional[AsyncNetworkScanner] = None,
    arp_cache_override: Optional[Dict[str, str]] = None,
    max_cooldown_sec: float = MAX_COOLDOWN_SEC,
) -> Optional[str]:
    """
    RTSP 연결 3회 연속 실패 시 격발되는 자율 힐링(Auto-Healing) 엔진.
    1. 지수 백오프 쿨다운(10s -> 20s -> ... 최대 300s) 검사로 무한 스캔 루프 방어
    2. 로컬 축사 LAN(ARP/ONVIF) 비동기 스캔으로 대상 카메라의 새 IP 획득
    3. hoodyfarm.yaml 내 RTSP URL 0초 치환 저장 (백업 .bak 생성)
    4. WorkerManager 활성 시 인메모리 프로파일 Hot-Reload 트리거
    5. 새 IP 반환 (미발견 또는 쿨다운 중일 시 None 반환)
    """
    now = time.time()
    state = _AUTO_HEAL_STATE.setdefault(
        camera_id,
        {"last_attempt": 0.0, "failures": 0, "cooldown": INITIAL_COOLDOWN_SEC},
    )

    last_attempt = state["last_attempt"]
    current_cooldown = state["cooldown"]

    if last_attempt > 0 and (now - last_attempt) < current_cooldown:
        remaining = current_cooldown - (now - last_attempt)
        logger.warning(
            f"[{camera_id}] 자율 힐링 쿨다운 활성 중 (남은 시간: {remaining:.1f}초, 현재 쿨다운: {current_cooldown:.1f}초). 스캔을 건너뜁니다."
        )
        return None

    state["last_attempt"] = now
    logger.info(f"🚨 [{camera_id}] 스트림 수신 실패 3회 감지: ONVIF/ARP 자율 재연결(Auto-Healing) 탐색 가동...")

    # 1. 새 IP 탐색
    net_scanner = scanner or AsyncNetworkScanner()
    resolved_ip = net_scanner.resolve_camera_ip(camera_id, arp_cache_override=arp_cache_override)

    if not resolved_ip:
        # ARP에 없으면 전체 스캔 시도
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 이벤트 루프가 돌고 있는 경우 (FastAPI 비동기 컨텍스트 등)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    discovered = pool.submit(
                        asyncio.run, net_scanner.scan_and_resolve(arp_cache_override=arp_cache_override)
                    ).result()
            else:
                discovered = loop.run_until_complete(
                    net_scanner.scan_and_resolve(arp_cache_override=arp_cache_override)
                )
        except Exception:
            try:
                discovered = asyncio.run(
                    net_scanner.scan_and_resolve(arp_cache_override=arp_cache_override)
                )
            except Exception as e:
                logger.error(f"[{camera_id}] 스캐너 실행 중 오류: {e}")
                discovered = []

        for cam in discovered:
            if cam.camera_id == camera_id and cam.current_ip:
                resolved_ip = cam.current_ip
                break

    # 2. 결과 판정 및 지수 백오프 갱신
    if not resolved_ip:
        state["failures"] += 1
        new_cd = min(max_cooldown_sec, INITIAL_COOLDOWN_SEC * (2 ** (state["failures"] - 1)))
        state["cooldown"] = new_cd
        logger.warning(
            f"⚠️ [{camera_id}] 장비 탐색 실패 (누적 실패: {state['failures']}회). "
            f"다음 재시도 쿨다운 {new_cd:.1f}초 적용 (최대 {max_cooldown_sec}초)."
        )
        return None

    # 성공: 쿨다운 초기화
    state["failures"] = 0
    state["cooldown"] = INITIAL_COOLDOWN_SEC
    logger.info(f"✅ [{camera_id}] 새 활성 IP 발견: {resolved_ip}")

    # 3. YAML 파일 갱신
    target_yaml = yaml_path or settings.FARM_PROFILE_PATH or "config/farms/hoodyfarm.yaml"
    _update_camera_yaml(camera_id, resolved_ip, target_yaml)

    # 4. WorkerManager Hot-Reload 시도 (동작 중인 경우)
    try:
        from src.services.worker_manager import worker_manager
        from src.domain.models.farm_profile import FarmProfile

        if os.path.exists(target_yaml):
            new_profile = FarmProfile.from_yaml(target_yaml)
            worker_manager.reload_from_profile(new_profile)
            logger.info(f"[{camera_id}] WorkerManager 인메모리 파이프라인 핫리로드 완료.")
    except Exception as e:
        logger.debug(f"WorkerManager 핫리로드 생략 또는 실패: {e}")

    return resolved_ip


def _update_camera_yaml(camera_id: str, new_ip: str, yaml_path: str):
    """YAML 파일 내 특정 카메라의 IP를 새 IP로 치환하고 백업 생성."""
    if not os.path.exists(yaml_path):
        logger.warning(f"설정 파일({yaml_path})이 존재하지 않아 파일 저장을 건너뜁니다.")
        return

    try:
        # 백업 생성
        backup_path = f"{yaml_path}.bak"
        shutil.copy2(yaml_path, backup_path)

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        cams = data.get("cameras", [])
        updated = False
        for entry in cams:
            if entry.get("camera_id") == camera_id:
                old_url = entry.get("rtsp_url", "")
                new_url = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", new_ip, old_url)
                if old_url != new_url:
                    entry["rtsp_url"] = new_url
                    updated = True
                    logger.info(f"[{camera_id}] YAML RTSP URL 갱신: {old_url} ➔ {new_url}")

        if updated:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            logger.info(f"[{camera_id}] {yaml_path} 저장 완료.")
    except Exception as e:
        logger.error(f"[{camera_id}] YAML 파일 갱신 중 오류: {e}")


class VideoStreamHandler:
    """
    RTSP / CCTV Video Stream Handler using OpenCV.
    Captures live stream frames, handles 3-strike auto-reconnection/auto-healing,
    keyframe sampling, motion detection, and synthetic frame generation for testing.
    """

    def __init__(
        self,
        stream_url: Optional[str] = None,
        camera_id: str = "CAM_BARN_01",
        yaml_path: Optional[str] = None,
    ):
        self.stream_url = stream_url or settings.RTSP_STREAM_URL
        self.camera_id = camera_id
        self.yaml_path = yaml_path
        self.max_reconnect_attempts = settings.MAX_RTSP_RECONNECT_ATTEMPTS
        self.consecutive_failures = 0
        self._cap: Optional[cv2.VideoCapture] = None

    def update_stream_url(self, new_url: str):
        """0초 핫리로드: 스트림 URL 교체 및 기존 VideoCapture 리소스 재할당."""
        logger.info(f"[{self.camera_id}] VideoStreamHandler URL 핫리로드: {self.stream_url} ➔ {new_url}")
        self.stream_url = new_url
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.consecutive_failures = 0

    def trigger_auto_healing_if_needed(self) -> Optional[str]:
        """연속 3회 실패 시 자율 힐링 격발."""
        if self.consecutive_failures >= 3:
            logger.warning(
                f"[{self.camera_id}] 연속 {self.consecutive_failures}회 실패 감지! 자율 힐링 격발..."
            )
            new_ip = auto_heal_camera_ip(self.camera_id, yaml_path=self.yaml_path)
            if new_ip:
                # 새 IP로 URL 치환
                new_url = re.sub(
                    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                    new_ip,
                    self.stream_url,
                )
                self.update_stream_url(new_url)
                return new_ip
        return None

    def capture_single_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from the RTSP stream.
        Returns NumPy array (BGR frame) or None if stream is unavailable.
        """
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            logger.warning(f"Could not open RTSP stream at {self.stream_url}")
            self.consecutive_failures += 1
            self.trigger_auto_healing_if_needed()
            return None

        try:
            success, frame = cap.read()
            if success and frame is not None:
                self.consecutive_failures = 0
                return frame
            else:
                self.consecutive_failures += 1
                self.trigger_auto_healing_if_needed()
                return None
        finally:
            cap.release()

    def capture_frame_with_retry(
        self, max_retries: Optional[int] = None, delay_sec: float = 1.0
    ) -> Tuple[Optional[np.ndarray], bool]:
        """
        Capture a frame with automatic retry & auto-heal logic.
        Returns (frame, is_synthetic_fallback).
        """
        retries = max_retries or self.max_reconnect_attempts

        for attempt in range(1, retries + 1):
            frame = self.capture_single_frame()
            if frame is not None:
                return frame, False

            logger.warning(
                f"RTSP frame capture failed (Attempt {attempt}/{retries}). Retrying in {delay_sec}s..."
            )
            time.sleep(delay_sec)

        logger.warning(
            f"Failed to capture RTSP frame after {retries} attempts. Generating synthetic test frame for simulation."
        )
        return (
            self.generate_synthetic_test_frame("RTSP Stream Offline - Simulation Frame"),
            True,
        )

    def calculate_motion_delta(
        self, prev_frame: np.ndarray, curr_frame: np.ndarray
    ) -> float:
        """
        Calculate motion score between two consecutive frames using absolute difference.
        """
        try:
            gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            gray_curr = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

            gray_prev = cv2.GaussianBlur(gray_prev, (21, 21), 0)
            gray_curr = cv2.GaussianBlur(gray_curr, (21, 21), 0)

            frame_delta = cv2.absdiff(gray_prev, gray_curr)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

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
            ret, buffer = cv2.imencode(".jpg", frame, encode_param)
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
            self.consecutive_failures += 1
            self.trigger_auto_healing_if_needed()
            yield self._generate_fallback_mjpeg("CCTV Stream Offline")
            return

        try:
            while True:
                success, frame = cap.read()
                if not success or frame is None:
                    self.consecutive_failures += 1
                    healed_ip = self.trigger_auto_healing_if_needed()
                    if healed_ip:
                        # 0초 재할당
                        cap.release()
                        cap = cv2.VideoCapture(self.stream_url)
                        continue
                    break

                self.consecutive_failures = 0
                jpeg_bytes = self.frame_to_jpeg_bytes(frame)
                if jpeg_bytes:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + jpeg_bytes
                        + b"\r\n"
                    )
        finally:
            cap.release()

    generate_mjpeg_frames = generate_mjpeg_stream

    def generate_synthetic_test_frame(
        self, label: str = "SmartLife CCTV Test Stream"
    ) -> np.ndarray:
        """
        Generate a synthetic 640x480 test image frame with timestamp and grid for testing.
        """
        img = np.zeros((480, 640, 3), dtype=np.uint8)

        img[:, :] = (30, 40, 25)

        for y in range(0, 480, 60):
            cv2.line(img, (0, y), (640, y), (50, 60, 45), 1)
        for x in range(0, 640, 80):
            cv2.line(img, (x, 0), (x, 480), (50, 60, 45), 1)

        cv2.rectangle(img, (20, 20), (620, 80), (70, 90, 60), -1)
        cv2.putText(
            img, label, (30, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
        cv2.putText(
            img,
            f"Timestamp: {now_str}",
            (30, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            1,
        )
        stream_display = (self.stream_url or "")[:40]
        cv2.putText(
            img,
            f"Stream URL: {stream_display}...",
            (30, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )

        cv2.rectangle(img, (220, 240), (420, 380), (0, 200, 255), 2)
        cv2.putText(
            img,
            "Simulated Object [CCTV Test]",
            (230, 230),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 200, 255),
            1,
        )

        return img

    def _generate_fallback_mjpeg(self, message: str) -> bytes:
        """
        Create fallback MJPEG chunk for offline streaming.
        """
        img = self.generate_synthetic_test_frame(message)
        jpeg_bytes = self.frame_to_jpeg_bytes(img) or b""
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg_bytes
            + b"\r\n"
        )
