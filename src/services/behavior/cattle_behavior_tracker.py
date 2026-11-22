"""Cattle Behavior Tracker using Fine-tuned YOLO, ByteTrack, and State Machine.

Detects:
1. Normal rest (lying_sternal)
2. Colic / Restlessness (frequent posture transitions between standing and lying_sternal)
3. Inverted cattle / Acute bloat (lying_lateral sustained for >= 15 seconds)
"""

from collections import Counter, deque
from dataclasses import dataclass, field
import logging
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 1. 자세 클래스 매핑 (파인튜닝 모델 기준)
CLASS_STANDING = 0       # 기립
CLASS_LYING_STERNAL = 1  # 정상 엎드림 (흉와)
CLASS_LYING_LATERAL = 2  # 옆으로 쓰러짐 / 뒤집힘 (측와 - 질식/폐사 위험)

# 2. 임계치 설정 (현장 튜닝 파라미터)
DEBOUNCE_WINDOW = 5             # 자세 확정용 최근 프레임 수 (2.5fps 기준 약 2초)
COLIC_WINDOW_SEC = 900          # 산통 전조 감시 윈도우 (15분 = 900초)
COLIC_TRANSITION_THRESHOLD = 4  # 15분 내 눕기/일어서기 전환 4회 이상 시 산통 경보
INVERTED_HOLD_SEC = 15.0        # 측와(뒤집힘) 자세 15초 이상 지속 시 긴급 경보
ALERT_COOLDOWN_SEC = 300.0      # 동일 개체 중복 알람 방지 쿨다운 (5분 = 300초)
STALE_TRACK_EXPIRY_SEC = 3600.0 # 미탐지 트랙 상태 메모리 보관 한도 (1시간)


@dataclass
class CattleTrackState:
    """개체별 시계열 상태 추적 머신."""
    track_id: int
    raw_history: deque = field(default_factory=lambda: deque(maxlen=DEBOUNCE_WINDOW))
    confirmed_posture: Optional[int] = None
    last_seen_time: float = 0.0

    # 시계열 이벤트 기록
    transition_timestamps: deque = field(default_factory=deque)  # 자세 전환 시각 기록
    lateral_start_time: Optional[float] = None                   # 측와 시작 시각

    # 중복 알림 방지 쿨다운
    last_colic_alert_at: float = 0.0
    last_inverted_alert_at: float = 0.0

    def update(self, raw_cls: int, now: Optional[float] = None) -> Optional[dict]:
        """프레임별 탐지 클래스를 받아 디바운싱 후 이상행동 이벤트를 반환.

        Args:
            raw_cls: 모델 혹은 보정 로직에서 입력된 단일 프레임 클래스 ID
            now: 현재 타임스탬프 (테스트 재현성을 위해 파라미터 허용)

        Returns:
            이상 행동 경보 딕셔너리 또는 None
        """
        if now is None:
            now = time.time()
        self.last_seen_time = now

        self.raw_history.append(raw_cls)
        if len(self.raw_history) < DEBOUNCE_WINDOW:
            return None

        # 다수결 디바운싱으로 현재 확정 자세 도출 (저해상도 서브스트림 노이즈 및 Jitter 방지)
        most_common_cls, count = Counter(self.raw_history).most_common(1)[0]
        if count < (DEBOUNCE_WINDOW // 2 + 1):
            return None

        prev_posture = self.confirmed_posture
        self.confirmed_posture = most_common_cls

        # 자세 전환(Standing <-> Lying_Sternal) 카운팅 (장꼬임/산통 전조 탐지)
        if prev_posture is not None and prev_posture != self.confirmed_posture:
            # 기립과 흉와 간의 전환이 포함된 경우 타임스탬프 누적
            if {prev_posture, self.confirmed_posture} & {CLASS_STANDING, CLASS_LYING_STERNAL}:
                self.transition_timestamps.append(now)

        # 윈도우(15분) 밖의 오래된 전환 기록 제거
        while self.transition_timestamps and (now - self.transition_timestamps[0] > COLIC_WINDOW_SEC):
            self.transition_timestamps.popleft()

        # [판정 1 - 최우선 긴급] 기립불능 / 급성 고창증 (측와 자세 15초 지속)
        if self.confirmed_posture == CLASS_LYING_LATERAL:
            if self.lateral_start_time is None:
                self.lateral_start_time = now
            elif (now - self.lateral_start_time) >= INVERTED_HOLD_SEC:
                if (now - self.last_inverted_alert_at) >= ALERT_COOLDOWN_SEC:
                    self.last_inverted_alert_at = now
                    return {
                        "alert_type": "CATTLE_INVERTED",
                        "severity": "CRITICAL",
                        "track_id": self.track_id,
                        "duration_sec": round(now - self.lateral_start_time, 1),
                        "message": f"[긴급] 개체 #{self.track_id} 측와(기립불능) {INVERTED_HOLD_SEC}초 이상 지속! 즉시 확인 요망"
                    }
        else:
            self.lateral_start_time = None

        # [판정 2 - 조기 예찰] 장꼬임 / 산통 전조 (15분 내 반복 기립·횡와)
        if len(self.transition_timestamps) >= COLIC_TRANSITION_THRESHOLD:
            if (now - self.last_colic_alert_at) >= ALERT_COOLDOWN_SEC:
                self.last_colic_alert_at = now
                return {
                    "alert_type": "COLIC_SUSPECTED",
                    "severity": "WARNING",
                    "track_id": self.track_id,
                    "transitions": len(self.transition_timestamps),
                    "message": f"[산통의심] 개체 #{self.track_id} 15분 내 {len(self.transition_timestamps)}회 반복 기립/횡와 감지 (고창증·장꼬임 전조)"
                }

        return None


class ZoneBehaviorMonitor:
    """우방(크롭된 뷰) 1개당 독립적으로 동작하는 ByteTrack 상태 관리자."""

    def __init__(
        self,
        zone_id: str,
        model_path: Optional[str] = None,
        tracker_cfg: str = "config/cattle_bytetrack.yaml",
        model: Optional[Any] = None,
    ):
        self.zone_id = zone_id
        self.tracker_cfg = tracker_cfg
        self.tracks: Dict[int, CattleTrackState] = {}

        if model is not None:
            self.model = model
        elif model_path:
            from ultralytics import YOLO
            self.model = YOLO(model_path, task="detect")
        else:
            self.model = None

    def process_detections(
        self,
        track_ids: List[int],
        classes: List[int],
        xyxys: List[List[float]],
        now: Optional[float] = None,
    ) -> List[dict]:
        """추적 결과(ID, 클래스, 바운딩 박스)를 입력받아 상태 머신을 갱신하고 경보 목록을 반환."""
        if now is None:
            now = time.time()
        alerts: List[dict] = []
        active_ids = set()

        for tid, cls_id, bbox in zip(track_ids, classes, xyxys):
            active_ids.add(tid)
            if tid not in self.tracks:
                self.tracks[tid] = CattleTrackState(track_id=tid)

            # 보조 휴리스틱: 저해상도에서 바운딩 박스 종횡비(가로/세로)가 극단적으로 납작하면 측와 가중치 보정
            x1, y1, x2, y2 = bbox
            aspect_ratio = (x2 - x1) / max((y2 - y1), 1.0)
            if cls_id == CLASS_LYING_STERNAL and aspect_ratio > 2.3:
                cls_id = CLASS_LYING_LATERAL

            event = self.tracks[tid].update(cls_id, now)
            if event:
                event["zone_id"] = self.zone_id
                event["bbox"] = [round(v, 1) for v in bbox]
                alerts.append(event)

        # 오랫동안 화면에서 사라진 오래된 트랙 메모리 정리 (1시간 이상 미탐지)
        stale_ids = [
            tid for tid, st in self.tracks.items()
            if tid not in active_ids and (now - st.last_seen_time > STALE_TRACK_EXPIRY_SEC)
        ]
        for tid in stale_ids:
            del self.tracks[tid]

        return alerts

    def process_frame(self, crop_frame: np.ndarray, now: Optional[float] = None) -> List[dict]:
        """640x360 크롭 프레임을 입력받아 YOLO+ByteTrack 추론 후 이상행동 경보 리스트 반환."""
        if self.model is None:
            raise RuntimeError("Model is not initialized in ZoneBehaviorMonitor.")

        # persist=True로 프레임 간 ByteTrack 칼만 필터 및 ID 영속성 유지
        results = self.model.track(
            source=crop_frame,
            imgsz=640,
            conf=0.45,
            iou=0.5,
            tracker=self.tracker_cfg,
            persist=True,
            verbose=False,
        )

        if not results or results[0].boxes is None or results[0].boxes.id is None:
            return []

        boxes = results[0].boxes
        track_ids = boxes.id.int().cpu().tolist()
        classes = boxes.cls.int().cpu().tolist()
        xyxys = boxes.xyxy.cpu().tolist()

        return self.process_detections(track_ids, classes, xyxys, now=now)
