"""Scheduler shared between the FastAPI lifespan (cron) and the 'Run Now'
route (manual trigger) so both paths run the exact same job function."""

from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from jobapply import config
from jobapply.agents.applier import run_applier
from jobapply.agents.finder import run_finder
from jobapply.agents.gap_advisor import run_gap_analysis
from jobapply.agents.tailor import run_tailor
from jobapply.db.models import PipelineRun
from jobapply.db.session import session_scope

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
PIPELINE_JOB_ID = "pipeline"
GAP_ADVISOR_JOB_ID = "gap_advisor"


def run_pipeline_job(trigger_source: str = "cron") -> dict[str, dict[str, int] | None]:
    """Finder, then tailor, then applier, in one run. A job goes from
    'found' all the way to 'pending_approval' (with an ntfy push)
    unattended; applier only ever acts on jobs already in 'approved' status
    - i.e. ones you've explicitly tapped Approve on - so the human review
    gate stays intact even though this chains everything after it.

    Every run is recorded as a PipelineRun row (stats + any error per
    stage), so a failure is visible on the dashboard instead of only in the
    server log."""
    started_at = dt.datetime.now(dt.timezone.utc)
    results: dict[str, tuple[dict[str, int] | None, str | None]] = {}

    # Built here (not at module level) so tests can monkeypatch
    # scheduler.run_finder/run_tailor/run_applier and have it take effect -
    # a module-level tuple would freeze in the original function objects.
    stages = (("finder", run_finder), ("tailor", run_tailor), ("applier", run_applier))
    for name, fn in stages:
        try:
            stats = fn()
            logger.info("%s run complete: %s", name, stats)
            results[name] = (stats, None)
        except Exception as exc:
            logger.exception("%s run failed", name)
            results[name] = (None, str(exc))

    with session_scope() as session:
        session.add(
            PipelineRun(
                trigger=trigger_source,
                started_at=started_at,
                finished_at=dt.datetime.now(dt.timezone.utc),
                finder_stats=results["finder"][0],
                finder_error=results["finder"][1],
                tailor_stats=results["tailor"][0],
                tailor_error=results["tailor"][1],
                applier_stats=results["applier"][0],
                applier_error=results["applier"][1],
            )
        )

    return {name: stats for name, (stats, _error) in results.items()}


def reschedule_finder() -> None:
    cron = config.get_setting("scheduler.finder_cron") or "0 8-22/3 * * *"
    timezone = config.get_setting("scheduler.timezone") or "UTC"
    if scheduler.get_job(PIPELINE_JOB_ID):
        scheduler.remove_job(PIPELINE_JOB_ID)
    scheduler.add_job(
        run_pipeline_job,
        CronTrigger.from_crontab(cron, timezone=timezone),
        id=PIPELINE_JOB_ID,
        kwargs={"trigger_source": "cron"},
    )


def trigger_pipeline_now() -> None:
    """Used by the dashboard's 'Run Now' button — runs once, immediately, outside the cron schedule."""
    scheduler.add_job(
        run_pipeline_job, id=f"{PIPELINE_JOB_ID}-manual", replace_existing=True, kwargs={"trigger_source": "manual"}
    )


def reschedule_gap_advisor() -> None:
    """Independent schedule from the job-search pipeline above - the Gap
    Advisor runs weekly by default, not every few hours."""
    cron = config.get_setting("scheduler.gap_advisor_cron") or "0 9 * * 1"
    timezone = config.get_setting("scheduler.timezone") or "UTC"
    if scheduler.get_job(GAP_ADVISOR_JOB_ID):
        scheduler.remove_job(GAP_ADVISOR_JOB_ID)
    scheduler.add_job(
        run_gap_analysis,
        CronTrigger.from_crontab(cron, timezone=timezone),
        id=GAP_ADVISOR_JOB_ID,
        kwargs={"trigger": "cron"},
    )


def trigger_gap_analysis_now() -> None:
    """Used by the dashboard's 'Run now' button on the Gaps page."""
    scheduler.add_job(
        run_gap_analysis, id=f"{GAP_ADVISOR_JOB_ID}-manual", replace_existing=True, kwargs={"trigger": "manual"}
    )
