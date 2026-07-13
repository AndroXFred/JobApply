"""Push notification for the approval gate.

Deliberately view-only: the notification carries no auth/approve action
(see the plan's "Approval gate security" note - an action button's auth
token would transit the notification payload itself, a spoofing/leak risk
on lock-screen previews and, on the public ntfy.sh relay, "topic name is
your only secret"). Approve/reject only ever happens as an authenticated
POST from inside the dashboard session.
"""

from __future__ import annotations

import logging

import httpx

from jobapply import config
from jobapply.db.models import Job

logger = logging.getLogger(__name__)


def publish(job: Job, fit_score: int | None = None) -> None:
    topic = config.get_setting("notify.ntfy.topic")
    if not topic:
        logger.warning("ntfy: no topic configured, skipping notification for job %s", job.id)
        return

    base_url = (config.get_setting("notify.ntfy.base_url") or "https://ntfy.sh").rstrip("/")
    dashboard_base = (config.get_setting("dashboard.base_url") or "http://localhost:8000").rstrip("/")
    job_url = f"{dashboard_base}/jobs/{job.id}"

    score_line = f"Fit score: {fit_score}. " if fit_score is not None else ""
    headers = {
        "Title": f"Review: {job.title} at {job.company}",
        "Click": job_url,
        "Actions": f"view, Open in dashboard, {job_url}",
        "Tags": "briefcase",
    }
    auth_token = config.get_setting("notify.ntfy.auth_token")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        httpx.post(
            f"{base_url}/{topic}",
            content=f"{score_line}Tap to review the tailored resume and approve or reject.".encode(),
            headers=headers,
            timeout=15.0,
        )
    except httpx.HTTPError:
        logger.exception("ntfy: failed to publish notification for job %s", job.id)
