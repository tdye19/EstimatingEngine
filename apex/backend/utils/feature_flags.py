"""Feature flag utilities for Sprint 17 demo mode.

Controlled by APEX_DEMO_MODE env var. When true, certain UI-facing routes return
404 so the frontend hides those tabs. The underlying pipeline agents continue to
run; only the surface is gated.
"""
from apex.backend.config import APEX_DEMO_MODE

HIDDEN_IN_DEMO = {
    "field_calibration",
    "shadow_comparison",
    "cost_tracking",
}


def demo_mode_enabled() -> bool:
    return APEX_DEMO_MODE


def feature_visible(feature_name: str) -> bool:
    """Return False if demo mode hides this feature, True otherwise."""
    if APEX_DEMO_MODE and feature_name in HIDDEN_IN_DEMO:
        return False
    return True
