"""Notification settings router — configure email alert preferences."""

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import APIResponse

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_auth)],
)


class NotificationSettingsOut(BaseModel):
    enabled: bool
    email_configured: bool
    smtp_host: str
    smtp_port: int
    notification_email: str | None = None
    triggers: dict


@router.get("/settings", response_model=APIResponse)
def get_notification_settings():
    """Return current notification configuration (no secrets)."""
    enabled = os.getenv("NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes")
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    email_configured = bool(os.getenv("SMTP_FROM") or os.getenv("SMTP_HOST") != "localhost")
    notification_email = os.getenv("NOTIFICATION_EMAIL")

    settings = NotificationSettingsOut(
        enabled=enabled,
        email_configured=email_configured,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        notification_email=notification_email,
        triggers={
            "pipeline_complete": True,
            "high_variance": True,
            "change_order_status": True,
        },
    )
    return APIResponse(success=True, data=settings.model_dump())


@router.post("/test", response_model=APIResponse)
def send_test_notification(current_user=Depends(require_auth)):
    """Send a test email to verify SMTP configuration."""
    from apex.backend.services.email_service import send_email

    to = os.getenv("NOTIFICATION_EMAIL", current_user.email)
    if not to:
        return APIResponse(
            success=False,
            error="No notification email configured. Set NOTIFICATION_EMAIL env var.",
        )

    sent = send_email(
        to=to,
        subject="[APEX] Test Notification",
        body_html="""
        <html><body style="font-family:sans-serif;">
        <h2 style="color:#1e40af;">APEX Test Notification</h2>
        <p>Your notification settings are configured correctly.</p>
        <p>You will receive alerts for pipeline completion and high-variance items.</p>
        </body></html>
        """,
    )

    if sent:
        return APIResponse(success=True, message=f"Test email sent to {to}")
    else:
        return APIResponse(
            success=False,
            error="Email not sent. Check NOTIFICATIONS_ENABLED and SMTP settings.",
        )
