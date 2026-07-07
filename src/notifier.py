"""
Notification system — sends alerts via Slack webhook or email (SMTP).
Used after weekly diff runs to alert on new competitors or rank changes.
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


def _slack_webhook() -> str:
    return os.getenv("SLACK_WEBHOOK_URL", "")


def _email_config() -> dict:
    return {
        "host":     os.getenv("SMTP_HOST", ""),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "to":       os.getenv("ALERT_EMAIL", ""),
    }


def send_slack(message: str, blocks: list | None = None) -> bool:
    """Post a message to Slack via webhook. Returns True on success."""
    webhook = _slack_webhook()
    if not webhook:
        return False

    payload = {"text": message}
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_email(subject: str, body: str, html: bool = False) -> bool:
    """Send an email alert. Returns True on success."""
    cfg = _email_config()
    if not all([cfg["host"], cfg["user"], cfg["password"], cfg["to"]]):
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]

    mime_type = "html" if html else "plain"
    msg.attach(MIMEText(body, mime_type))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"  [Notifier] Email failed: {e}")
        return False


def notify_run_complete(
    competitors_count: int,
    analyses_count: int,
    csv_path: str,
    new_competitors: list[str] | None = None,
) -> None:
    """Send completion notification after a full run."""
    new_str = ""
    if new_competitors:
        new_str = f"\n🆕 NEW COMPETITORS detected: {', '.join(new_competitors)}"

    message = (
        f"✅ Apostille Competitor Research — Run Complete\n"
        f"Competitors found: {competitors_count}\n"
        f"AI analyses done: {analyses_count}\n"
        f"CSV: {csv_path}"
        f"{new_str}"
    )

    sent_slack = send_slack(message)
    sent_email = send_email(
        subject="[Apostille Research] Run Complete",
        body=message,
    )

    if sent_slack or sent_email:
        print(f"  ✓ Notification sent (Slack={sent_slack}, Email={sent_email})")
    else:
        print("  – No notification sent (SLACK_WEBHOOK_URL and SMTP_* not configured)")


def notify_new_competitors(new_domains: list[str], run_date: str) -> None:
    """Alert when new competitors appear in the weekly diff."""
    if not new_domains:
        return

    lines = "\n".join(f"• {d}" for d in new_domains)
    message = (
        f"🚨 APOSTILLE RESEARCH ALERT — {run_date}\n"
        f"New competitors detected in Google US results:\n{lines}\n\n"
        f"Re-run the research tool to get full analysis."
    )

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "🚨 New Apostille Competitors Detected"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Date:* {run_date}\n*New domains:*\n{lines}"}},
    ]

    send_slack(message, blocks=blocks)
    send_email(
        subject=f"[Apostille Research] {len(new_domains)} New Competitors — {run_date}",
        body=message,
    )
