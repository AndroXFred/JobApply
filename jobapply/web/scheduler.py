"""Scheduler shared between the FastAPI lifespan (cron) and the 'Run Now'
route (manual trigger) so both paths run the exact same job function."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from jobapply import config
from jobapply.agents.finder import run_finder

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
FINDER_JOB_ID = "finder"


def run_finder_job() -> dict[str, int] | None:
    try:
        stats = run_finder()
        logger.info("finder run complete: %s", stats)
        return stats
    except Exception:
        logger.exception("finder run failed")
        return None


def reschedule_finder() -> None:
    cron = config.get_setting("scheduler.finder_cron") or "0 8-22/3 * * *"
    timezone = config.get_setting("scheduler.timezone") or "UTC"
    if scheduler.get_job(FINDER_JOB_ID):
        scheduler.remove_job(FINDER_JOB_ID)
    scheduler.add_job(
        run_finder_job, CronTrigger.from_crontab(cron, timezone=timezone), id=FINDER_JOB_ID
    )


def trigger_finder_now() -> None:
    """Used by the dashboard's 'Run Now' button — runs once, immediately, outside the cron schedule."""
    scheduler.add_job(run_finder_job, id=f"{FINDER_JOB_ID}-manual", replace_existing=True)
