"""Email notifications for new jobs via the Gmail API (OAuth).

Uses Google's Gmail REST API over HTTPS (port 443) instead of SMTP, because
platforms like Render block outbound SMTP ports (25/465/587).
"""

from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from typing import List

import requests

from .models import Job

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _render_job_html(job: Job) -> str:
    logo = (
        f'<img src="{job.logo_url}" width="56" height="56" '
        f'style="border-radius:4px;margin-right:15px;float:left;" alt="">'
        if job.logo_url
        else ""
    )
    posted = job.listed_at.strftime("%Y-%m-%d %H:%M UTC") if job.listed_at else ""
    return f"""
    <div style="margin-bottom:20px;padding:15px;border:1px solid #ddd;border-radius:5px;overflow:hidden;">
        {logo}
        <div style="overflow:hidden;">
            <h3 style="margin:0;color:#0a66c2;">
                <a href="{job.url}" style="text-decoration:none;color:#0a66c2;">{job.title}</a>
            </h3>
            <p style="margin:5px 0 0 0;"><strong>{job.company}</strong></p>
            <p style="margin:5px 0 0 0;color:#666;">{job.location}</p>
            <p style="margin:5px 0 0 0;color:#888;font-size:0.9em;">{job.metadata_text}{(' · ' + posted) if posted else ''}</p>
        </div>
    </div>
    """


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _build_raw_message(
    sender_email: str,
    receivers: List[str],
    subject: str,
    html: str,
) -> str:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(receivers)
    msg.set_content("Please enable HTML viewing to see this email.")
    msg.add_alternative(html, subtype="html")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_jobs_email(
    jobs: List[Job],
    sender_email: str,
    receiver_email: str,
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> None:
    """Send an HTML email listing the given jobs."""
    if not jobs:
        return

    receivers = [r.strip() for r in receiver_email.split(",") if r.strip()]
    subject = f"LinkedIn Alert: {len(jobs)} New Job{'s' if len(jobs) > 1 else ''} Found!"

    body = "".join(_render_job_html(job) for job in jobs)
    html = (
        f"<html><body style='font-family:Arial,sans-serif;color:#333;'>"
        f"<h2>Found {len(jobs)} New Job{'s' if len(jobs) > 1 else ''}</h2><hr>{body}</body></html>"
    )
    raw = _build_raw_message(sender_email, receivers, subject, html)

    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)
        resp = requests.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.error("Gmail API error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        logger.info("Sent email to %s with %d jobs.", receiver_email, len(jobs))
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
