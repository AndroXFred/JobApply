"""Agent 1: find postings across all enabled sources, dedupe, score fit.

Every job found is persisted, including rejected ones, so the dashboard
stays a complete record of what was seen and why it was (or wasn't)
pursued.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from sqlalchemy import select

from jobapply import config
from jobapply.db.models import Evaluation, Job, StatusHistory
from jobapply.db.session import session_scope
from jobapply.llm.client import OpenAICompatClient, get_client_for
from jobapply.llm.schemas import JobEvaluation
from jobapply.resume.loader import load_master_resume_text
from jobapply.sources.base import RawJob
from jobapply.sources.registry import ALL_SOURCES

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1"
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "finder_system.md"


def _system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _normalized_key(raw: RawJob) -> str:
    return "|".join(part.strip().lower() for part in (raw.company, raw.title, raw.remote_type or "unknown"))


def _record_status(session, job: Job, to_status: str, changed_by: str, note: str | None = None) -> None:
    session.add(
        StatusHistory(job_id=job.id, from_status=job.status, to_status=to_status, changed_by=changed_by, note=note)
    )
    job.status = to_status


def _upsert_job(session, raw: RawJob) -> tuple[int, bool]:
    """Returns (job_id, is_new)."""
    existing = session.scalar(select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id))
    if existing:
        existing.last_seen_at = _utcnow()
        existing.description_raw = raw.description_raw or existing.description_raw
        return existing.id, False

    normalized_key = _normalized_key(raw)
    duplicate_of = session.scalar(
        select(Job.id).where(Job.normalized_key == normalized_key, Job.source != raw.source).limit(1)
    )
    job = Job(
        source=raw.source,
        external_id=raw.external_id,
        company=raw.company,
        title=raw.title,
        location=raw.location,
        remote_type=raw.remote_type,
        url=raw.url,
        description_raw=raw.description_raw,
        salary_min=raw.salary_min,
        salary_max=raw.salary_max,
        posted_at=raw.posted_at,
        status="new",
        normalized_key=normalized_key,
        duplicate_of_job_id=duplicate_of,
        raw_json=raw.raw,
    )
    session.add(job)
    session.flush()
    _record_status(session, job, "new", changed_by="agent1", note=f"found via {raw.source}")
    return job.id, True


def _evaluate_job(client: OpenAICompatClient, model: str, job: Job, resume_text: str) -> JobEvaluation:
    user_prompt = (
        f"## Candidate resume\n{resume_text}\n\n"
        f"## Job posting\n"
        f"Company: {job.company}\nTitle: {job.title}\nLocation: {job.location or 'unspecified'}\n"
        f"Remote type: {job.remote_type or 'unknown'}\n"
        f"Salary range: {job.salary_min or 'unspecified'} - {job.salary_max or 'unspecified'}\n\n"
        f"Description:\n{job.description_raw or '(no description provided)'}"
    )
    return client.complete_json(system=_system_prompt(), user=user_prompt, response_schema=JobEvaluation, model=model)


def run_finder() -> dict[str, int]:
    resume_text = load_master_resume_text()
    threshold = config.get_int("scoring.fit_score_threshold") or 70
    client, model = get_client_for("finder")

    stats = {"found": 0, "new": 0, "evaluated": 0, "pursue": 0, "rejected": 0, "failed": 0}

    for source in ALL_SOURCES:
        try:
            raw_jobs = source.fetch()
        except Exception:
            logger.exception("source %s failed", getattr(source, "name", source))
            continue
        stats["found"] += len(raw_jobs)

        for raw in raw_jobs:
            with session_scope() as session:
                job_id, is_new = _upsert_job(session, raw)
            if not is_new:
                continue
            stats["new"] += 1

            with session_scope() as session:
                job = session.get(Job, job_id)
                try:
                    result = _evaluate_job(client, model, job, resume_text)
                except Exception:
                    logger.exception("evaluation failed for job %s", job_id)
                    _record_status(session, job, "evaluation_failed", changed_by="agent1")
                    stats["failed"] += 1
                    continue

                session.add(
                    Evaluation(
                        job_id=job.id,
                        fit_score=result.fit_score,
                        rationale=result.rationale,
                        red_flags=list(result.red_flags),
                        recommendation=result.recommendation,
                        llm_model=model,
                        prompt_version=PROMPT_VERSION,
                    )
                )
                stats["evaluated"] += 1
                if result.recommendation == "pursue" and result.fit_score >= threshold:
                    _record_status(session, job, "pending_tailor", changed_by="agent1")
                    stats["pursue"] += 1
                else:
                    _record_status(session, job, "rejected", changed_by="agent1")
                    stats["rejected"] += 1

    return stats
