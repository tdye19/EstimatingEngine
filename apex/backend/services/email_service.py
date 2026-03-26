"""Email notification service using SMTP."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apex.backend.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_ENABLED,
)

logger = logging.getLogger("apex.email")


def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email. Returns True on success, False on failure. Never raises."""
    if not EMAIL_ENABLED:
        logger.debug(f"Email disabled, skipping: {subject} -> {to}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to], msg.as_string())

        logger.info(f"Email sent: {subject} -> {to}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {subject} -> {to}: {e}")
        return False


def send_pipeline_complete(to: str, project_name: str, project_number: str, success: bool, error_msg: str = None):
    """Send pipeline completion notification."""
    status = "completed successfully" if success else "failed"
    color = "#16a34a" if success else "#dc2626"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1E40AF; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">APEX Platform</h1>
        </div>
        <div style="padding: 30px; background: #f9fafb;">
            <h2 style="color: #111827;">Pipeline {status.title()}</h2>
            <p>The estimating pipeline for <strong>{project_name}</strong> ({project_number}) has {status}.</p>
            {"<p style='color: " + color + ";'><strong>Error:</strong> " + (error_msg or "") + "</p>" if not success else ""}
            <p style="margin-top: 20px;">
                <a href="#" style="background: #1E40AF; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    View Project
                </a>
            </p>
        </div>
        <div style="padding: 15px; text-align: center; color: #6b7280; font-size: 12px;">
            APEX — Automated Project Estimation Exchange
        </div>
    </div>
    """

    subject = f"APEX: Pipeline {status} — {project_name}"
    return send_email(to, subject, html)


def send_estimate_ready(to: str, project_name: str, project_number: str, total_bid: float):
    """Send estimate ready notification."""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1E40AF; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">APEX Platform</h1>
        </div>
        <div style="padding: 30px; background: #f9fafb;">
            <h2 style="color: #111827;">Estimate Ready</h2>
            <p>A new estimate is ready for <strong>{project_name}</strong> ({project_number}).</p>
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                <p style="color: #6b7280; margin: 0 0 8px 0;">Total Bid Amount</p>
                <p style="font-size: 32px; font-weight: bold; color: #1E40AF; margin: 0;">
                    ${total_bid:,.2f}
                </p>
            </div>
            <p style="margin-top: 20px;">
                <a href="#" style="background: #1E40AF; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    View Estimate
                </a>
            </p>
        </div>
        <div style="padding: 15px; text-align: center; color: #6b7280; font-size: 12px;">
            APEX — Automated Project Estimation Exchange
        </div>
    </div>
    """

    subject = f"APEX: Estimate Ready — {project_name} (${total_bid:,.0f})"
    return send_email(to, subject, html)
