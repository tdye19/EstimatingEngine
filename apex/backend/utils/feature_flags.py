"""Feature flag helpers for demo mode gating."""

from apex.backend.config import APEX_DEMO_MODE

HIDDEN_IN_DEMO = {
    "field_calibration",
    "improve",
    "shadow_mode",
    "cost_tracking",
}


def demo_mode_enabled() -> bool:
    return APEX_DEMO_MODE


def feature_visible(feature_name: str) -> bool:
    if demo_mode_enabled() and feature_name in HIDDEN_IN_DEMO:
        return False
    return True
