"""Scheduler shared between the FastAPI lifespan (cron) and the 'Run Now'
route (manual trigger) so both paths run the exact same job function."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from jobapply import config
from jobapply.agents.finder import run_finder
from jobapply.agents.tailor import run_tailor

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
PIPELINE_JOB_ID = "pipeline"


def run_pipeline_job() -> dict[str, dict[str, int]] | None:
    """Finder then tailor in one run, so a scheduled/manual trigger takes a
    job all the way from 'found' to 'pending_approval' (with an ntfy push)
    without a separate step - only Agent 3's submission stays gated on your
    explicit approval."""
    try:
        finder_stats = run_finder()
        logger.info("finder run complete: %s", finder_stats)
    except Exception:
        logger.exception("finder run failed")
        finder_stats = None

    try:
        tailor_stats = run_tailor()
        logger.info("tailor run complete: %s", tailor_stats)
    except Exception:
        logger.exception("tailor run failed")
        tailor_stats = None

    if finder_stats is None and tailor_stats is None:
        return None
    return {"finder": finder_stats, "tailor": tailor_stats}


def reschedule_finder() -> None:
    cron = config.get_setting("scheduler.finder_cron") or "0 8-22/3 * * *"
    timezone = config.get_setting("scheduler.timezone") or "UTC"
    if scheduler.get_job(PIPELINE_JOB_ID):
        scheduler.remove_job(PIPELINE_JOB_ID)
    scheduler.add_job(
        run_pipeline_job, CronTrigger.from_crontab(cron, timezone=timezone), id=PIPELINE_JOB_ID
    )


def trigger_pipeline_now() -> None:
    """Used by the dashboard's 'Run Now' button — runs once, immediately, outside the cron schedule."""
    scheduler.add_job(run_pipeline_job, id=f"{PIPELINE_JOB_ID}-manual", replace_existing=True)
