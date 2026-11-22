"""Unit tests for Cattle Behavior Tracker."""

import time
import pytest

from src.services.behavior.cattle_behavior_tracker import (
    CLASS_STANDING,
    CLASS_LYING_STERNAL,
    CLASS_LYING_LATERAL,
    DEBOUNCE_WINDOW,
    COLIC_WINDOW_SEC,
    COLIC_TRANSITION_THRESHOLD,
    INVERTED_HOLD_SEC,
    ALERT_COOLDOWN_SEC,
    CattleTrackState,
    ZoneBehaviorMonitor,
)


def test_debouncing_requires_minimum_frames_and_majority():
    state = CattleTrackState(track_id=1)
    t = 1000.0

    # 1~4 프레임: DEBOUNCE_WINDOW(5) 미만이므로 확정되지 않음
    for i in range(4):
        res = state.update(CLASS_STANDING, now=t + i * 0.4)
        assert res is None
        assert state.confirmed_posture is None

    # 5번째 프레임 입력 (STANDING 5회 -> 과반수 이상)
    res = state.update(CLASS_STANDING, now=t + 1.6)
    assert res is None
    assert state.confirmed_posture == CLASS_STANDING

    # 1프레임 노이즈 (LYING_LATERAL) 유입 시 다수결로 무시됨
    state.update(CLASS_LYING_LATERAL, now=t + 2.0)
    assert state.confirmed_posture == CLASS_STANDING


def test_cattle_inverted_alert_after_15_seconds():
    state = CattleTrackState(track_id=10)
    t = 2000.0

    # 5프레임 측와(LYING_LATERAL) 입력하여 자세 확정
    for i in range(5):
        res = state.update(CLASS_LYING_LATERAL, now=t + i * 0.4)
        assert res is None

    assert state.confirmed_posture == CLASS_LYING_LATERAL
    assert state.lateral_start_time is not None

    start_lat = state.lateral_start_time

    # 14.9초 경과 -> 아직 임계치(15.0초) 미달
    res = state.update(CLASS_LYING_LATERAL, now=start_lat + 14.9)
    assert res is None

    # 15.0초 경과 -> CATTLE_INVERTED 긴급 경보 발생!
    alert = state.update(CLASS_LYING_LATERAL, now=start_lat + 15.0)
    assert alert is not None
    assert alert["alert_type"] == "CATTLE_INVERTED"
    assert alert["severity"] == "CRITICAL"
    assert alert["track_id"] == 10
    assert alert["duration_sec"] >= 15.0

    # 쿨다운 300초 이내에는 중복 경보 방지
    dup = state.update(CLASS_LYING_LATERAL, now=start_lat + 20.0)
    assert dup is None

    # 쿨다운 300초 이후에도 지속 중이면 재경보 (last_alert_at은 start_lat + 15.0 이었음)
    re_alert = state.update(CLASS_LYING_LATERAL, now=start_lat + 15.0 + 301.0)
    assert re_alert is not None
    assert re_alert["alert_type"] == "CATTLE_INVERTED"


def test_colic_suspected_alert_on_frequent_transitions():
    state = CattleTrackState(track_id=20)
    t = 3000.0

    def establish_posture(cls, current_t):
        for i in range(5):
            current_t += 0.4
            state.update(cls, now=current_t)
        return current_t

    # 1. 초기 자세: STANDING 확정
    t = establish_posture(CLASS_STANDING, t)
    assert state.confirmed_posture == CLASS_STANDING
    assert len(state.transition_timestamps) == 0

    # 2. 전환 1: STANDING -> LYING_STERNAL
    t = establish_posture(CLASS_LYING_STERNAL, t + 10.0)
    assert len(state.transition_timestamps) == 1

    # 3. 전환 2: LYING_STERNAL -> STANDING
    t = establish_posture(CLASS_STANDING, t + 10.0)
    assert len(state.transition_timestamps) == 2

    # 4. 전환 3: STANDING -> LYING_STERNAL
    t = establish_posture(CLASS_LYING_STERNAL, t + 10.0)
    assert len(state.transition_timestamps) == 3

    # 5. 전환 4: LYING_STERNAL -> STANDING (15분 내 4회째 전환 달성 -> 산통 의심 경보!)
    alert = None
    for i in range(5):
        t += 0.4
        res = state.update(CLASS_STANDING, now=t)
        if res:
            alert = res

    assert alert is not None
    assert alert["alert_type"] == "COLIC_SUSPECTED"
    assert alert["severity"] == "WARNING"
    assert alert["track_id"] == 20
    assert alert["transitions"] >= 4

    # 쿨다운(300초) 확인
    t = establish_posture(CLASS_LYING_STERNAL, t + 10.0)
    alert2 = None
    for i in range(5):
        t += 0.4
        res = state.update(CLASS_STANDING, now=t)
        if res:
            alert2 = res
    assert alert2 is None  # 쿨다운 중이므로 무시됨


def test_colic_window_expiration():
    state = CattleTrackState(track_id=30)
    t = 5000.0

    def establish_posture(cls, current_t):
        for i in range(5):
            current_t += 0.4
            state.update(cls, now=current_t)
        return current_t

    # t 시점에 2번 전환 발생
    t = establish_posture(CLASS_STANDING, t)
    t = establish_posture(CLASS_LYING_STERNAL, t + 1.0)
    t = establish_posture(CLASS_STANDING, t + 1.0)
    assert len(state.transition_timestamps) == 2

    # 15분(901초) 후 새 전환 발생
    t += 901.0
    t = establish_posture(CLASS_LYING_STERNAL, t)

    # 이전 900초 밖의 타임스탬프는 제거되어 1개만 남아있어야 함
    assert len(state.transition_timestamps) == 1


def test_zone_behavior_monitor_aspect_ratio_correction_and_cleanup():
    monitor = ZoneBehaviorMonitor(zone_id="cam01_zoneA", tracker_cfg="config/cattle_bytetrack.yaml")
    now = 10000.0

    # 흉와(LYING_STERNAL)이지만 bbox가 극단적으로 납작한 경우 (width=300, height=100 -> ratio 3.0 > 2.3)
    # 5프레임 공급하여 측와로 보정 확정 유도
    for i in range(5):
        alerts = monitor.process_detections(
            track_ids=[101],
            classes=[CLASS_LYING_STERNAL],
            xyxys=[[10.0, 10.0, 310.0, 110.0]],  # ratio = 300 / 100 = 3.0
            now=now + i * 0.4,
        )

    assert monitor.tracks[101].confirmed_posture == CLASS_LYING_LATERAL

    # 15초 유지 후 경보 확인 (확정 시점이 now + 1.6이므로 now + 1.6 + 15.0 이상 시점인 now + 18.0)
    alerts = monitor.process_detections(
        track_ids=[101],
        classes=[CLASS_LYING_STERNAL],
        xyxys=[[10.0, 10.0, 310.0, 110.0]],
        now=now + 18.0,
    )
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "CATTLE_INVERTED"
    assert alerts[0]["zone_id"] == "cam01_zoneA"

    # 오래된 트랙 정리 테스트 (3601초 경과 후 다른 활성 ID만 감지)
    monitor.process_detections(
        track_ids=[202],
        classes=[CLASS_STANDING],
        xyxys=[[50.0, 50.0, 150.0, 150.0]],
        now=now + 3700.0,
    )
    assert 101 not in monitor.tracks
    assert 202 in monitor.tracks
