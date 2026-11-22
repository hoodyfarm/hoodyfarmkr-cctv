"""Cattle behavior analysis package."""
from .cattle_behavior_tracker import (
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

__all__ = [
    "CLASS_STANDING",
    "CLASS_LYING_STERNAL",
    "CLASS_LYING_LATERAL",
    "DEBOUNCE_WINDOW",
    "COLIC_WINDOW_SEC",
    "COLIC_TRANSITION_THRESHOLD",
    "INVERTED_HOLD_SEC",
    "ALERT_COOLDOWN_SEC",
    "CattleTrackState",
    "ZoneBehaviorMonitor",
]
