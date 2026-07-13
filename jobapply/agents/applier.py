"""Agent 3: submit approved applications via Playwright.

Scoped to Greenhouse/Lever/Ashby only (see playwright_runner.detect_platform)
- these are templated ATS platforms with tractable, fairly consistent form
structure. Anything else (e.g. a JSearch-aggregated posting linking to an
arbitrary company career site) is left for you to apply to manually rather
than attempting unreliable generic automation. Never guesses an answer to
an unmapped required field - see form_filler.py / platforms/base.py.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select

from jobapply.applier import playwright_runner
from jobapply.applier.platforms.base import ApplyOutcome
from jobapply.db.models import Application, Job, TailoredResume
from jobapply.db.session import session_scope
from jobapply.db.status import record_status
from jobapply.resume.loader import load_master_resume

logger = logging.getLogger(__name__)


def _latest_tailored_resume(session, job_id: int) -> TailoredResume | None:
    return session.scalar(
        select(TailoredResume).where(TailoredResume.job_id == job_id).order_by(TailoredResume.created_at.desc())
    )


def run_applier(job_id: int | None = None) -> dict[str, int]:
    with session_scope() as session:
        query = select(Job.id).where(Job.status == "approved")
        if job_id is not None:
            query = query.where(Job.id == job_id)
        job_ids = list(session.scalars(query).all())

    resume = load_master_resume()
    stats = {"processed": 0, "applied": 0, "unsupported": 0, "failed": 0}

    for jid in job_ids:
        stats["processed"] += 1

        with session_scope() as session:
            job = session.get(Job, jid)
            tailored = _latest_tailored_resume(session, jid)
            record_status(session, job, "applying", changed_by="agent3")

            application = Application(
                job_id=jid,
                tailored_resume_id=tailored.id if tailored else None,
                ats_platform="unknown",
                status="pending",
                attempt_count=1,
            )
            session.add(application)
            session.flush()
            application_id = application.id
            job_url = job.url
            resume_pdf_path = tailored.pdf_path if tailored else None

        platform = playwright_runner.detect_platform(job_url)

        if platform is None or not resume_pdf_path:
            reason = (
                "No supported ATS platform detected for this job's URL - apply manually."
                if platform is None
                else "No tailored resume PDF available for this job."
            )
            with session_scope() as session:
                job = session.get(Job, jid)
                application = session.get(Application, application_id)
                application.ats_platform = platform or "unsupported"
                application.status = "failed"
                application.error_message = reason
                record_status(session, job, "apply_failed", changed_by="agent3", note=reason)
            stats["unsupported"] += 1
            continue

        with session_scope() as session:
            session.get(Application, application_id).ats_platform = platform

        try:
            outcome = playwright_runner.run_application(platform, job_url, resume_pdf_path, resume, job_id=jid)
        except Exception as exc:
            logger.exception("unexpected applier failure for job %s", jid)
            outcome = ApplyOutcome(status="error", error_message=f"Unexpected error: {exc}")

        with session_scope() as session:
            job = session.get(Job, jid)
            application = session.get(Application, application_id)
            application.confirmation_screenshot_path = outcome.screenshot_path

            if outcome.status == "submitted":
                application.status = "submitted"
                application.submitted_at = dt.datetime.now(dt.timezone.utc)
                application.confirmation_text = outcome.confirmation_text
                record_status(session, job, "applied", changed_by="agent3")
                stats["applied"] += 1
            else:
                application.status = "failed"
                if outcome.status == "unmappable_fields":
                    application.error_message = (
                        "Application form has fields Agent 3 doesn't know how to fill safely: "
                        + ", ".join(outcome.unmapped_fields)
                        + " - apply manually."
                    )
                else:
                    application.error_message = outcome.error_message or "Unknown failure."
                record_status(session, job, "apply_failed", changed_by="agent3", note=application.error_message)
                stats["failed"] += 1

    return stats
