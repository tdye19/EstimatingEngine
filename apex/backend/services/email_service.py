"""Email notification service.

Configure via environment variables:
    SMTP_HOST        default: localhost
    SMTP_PORT        default: 587
    SMTP_USERNAME    SMTP auth username (optional for local relay)
    SMTP_PASSWORD    SMTP auth password (optional for local relay)
    SMTP_FROM        From address, e.g. noreply@yourgc.com
    SMTP_USE_TLS     true/false (default true)
    NOTIFICATIONS_ENABLED  true/false (default false — opt-in)

When NOTIFICATIONS_ENABLED is not "true" all send calls are no-ops so the
rest of the system doesn't need to check the flag.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger("apex.email")


def _is_enabled() -> bool:
    return os.getenv("NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes")


def _build_message(to: str | list[str], subject: str, body_html: str, body_text: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", "noreply@apex-estimate.local")
    msg["To"] = ", ".join(to) if isinstance(to, list) else to
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    return msg


def send_email(to: str | list[str], subject: str, body_html: str, body_text: str = "") -> bool:
    """Send an email. Returns True on success, False on failure (never raises)."""
    if not _is_enabled():
        logger.debug("Email notifications disabled — skipping '%s'", subject)
        return False

    if not body_text:
        # Strip basic tags for plain-text fallback
        import re
        body_text = re.sub(r"<[^>]+>", "", body_html)

    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    recipients = to if isinstance(to, list) else [to]
    msg = _build_message(to, subject, body_html, body_text)

    try:
        if use_tls:
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls()
                if username:
                    server.login(username, password)
                server.sendmail(msg["From"], recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if username:
                    server.login(username, password)
                server.sendmail(msg["From"], recipients, msg.as_string())
        logger.info("Email sent to %s: %s", recipients, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", recipients, exc)
        return False


# ── Notification helpers ──────────────────────────────────────────────────────

def notify_pipeline_complete(
    to: str | list[str],
    project_name: str,
    project_number: str,
    total_bid: Optional[float] = None,
    variance_pct: Optional[float] = None,
):
    """Send a notification when the agent pipeline finishes."""
    bid_str = f"${total_bid:,.0f}" if total_bid else "N/A"
    var_str = f"{variance_pct:+.1f}%" if variance_pct is not None else "N/A"

    subject = f"[APEX] Pipeline complete — {project_name} ({project_number})"
    html = f"""
    <html><body style="font-family:sans-serif;color:#1e293b;">
    <h2 style="color:#1e40af;">APEX — Pipeline Complete</h2>
    <p>The estimating pipeline has finished for:</p>
    <table style="border-collapse:collapse;width:100%;max-width:500px;">
      <tr><td style="padding:6px 12px;font-weight:bold;">Project</td><td style="padding:6px 12px;">{project_name}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">Project #</td><td style="padding:6px 12px;">{project_number}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;">Total Bid</td><td style="padding:6px 12px;">{bid_str}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">Variance</td><td style="padding:6px 12px;">{var_str}</td></tr>
    </table>
    <p style="margin-top:20px;">Log in to APEX to review the full estimate.</p>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
    <p style="font-size:12px;color:#94a3b8;">APEX Automated Project Estimation Exchange</p>
    </body></html>
    """
    send_email(to, subject, html)


def notify_high_variance(
    to: str | list[str],
    project_name: str,
    project_number: str,
    csi_code: str,
    description: str,
    variance_pct: float,
):
    """Alert estimators when IMPROVE agent flags a high variance item."""
    subject = f"[APEX] High variance flagged — {project_name}"
    color = "#dc2626" if variance_pct > 20 else "#f59e0b"
    html = f"""
    <html><body style="font-family:sans-serif;color:#1e293b;">
    <h2 style="color:#1e40af;">APEX — High Variance Alert</h2>
    <p>The IMPROVE agent has flagged a significant variance for:</p>
    <table style="border-collapse:collapse;width:100%;max-width:500px;">
      <tr><td style="padding:6px 12px;font-weight:bold;">Project</td><td style="padding:6px 12px;">{project_name} ({project_number})</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">CSI Code</td><td style="padding:6px 12px;">{csi_code}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;">Item</td><td style="padding:6px 12px;">{description}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">Variance</td>
        <td style="padding:6px 12px;color:{color};font-weight:bold;">{variance_pct:+.1f}%</td></tr>
    </table>
    <p style="margin-top:20px;">Please review this line item before submitting the bid.</p>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
    <p style="font-size:12px;color:#94a3b8;">APEX Automated Project Estimation Exchange</p>
    </body></html>
    """
    send_email(to, subject, html)


def notify_change_order(
    to: str | list[str],
    project_name: str,
    co_number: str,
    co_title: str,
    cost_impact: float,
    status: str,
):
    """Notify when a change order is created or its status changes."""
    subject = f"[APEX] Change Order {co_number} — {status.title()} — {project_name}"
    color = "#16a34a" if status == "approved" else "#f59e0b" if status == "pending" else "#dc2626"
    html = f"""
    <html><body style="font-family:sans-serif;color:#1e293b;">
    <h2 style="color:#1e40af;">APEX — Change Order Update</h2>
    <table style="border-collapse:collapse;width:100%;max-width:500px;">
      <tr><td style="padding:6px 12px;font-weight:bold;">Project</td><td style="padding:6px 12px;">{project_name}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">CO #</td><td style="padding:6px 12px;">{co_number}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;">Title</td><td style="padding:6px 12px;">{co_title}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:6px 12px;font-weight:bold;">Cost Impact</td>
        <td style="padding:6px 12px;">${cost_impact:+,.0f}</td></tr>
      <tr><td style="padding:6px 12px;font-weight:bold;">Status</td>
        <td style="padding:6px 12px;color:{color};font-weight:bold;">{status.title()}</td></tr>
    </table>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
    <p style="font-size:12px;color:#94a3b8;">APEX Automated Project Estimation Exchange</p>
    </body></html>
    """
    send_email(to, subject, html)
