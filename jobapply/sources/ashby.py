"""Ashby public job board API. No auth, no scraping.

https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true

Field names below are based on Ashby's published API surface as of writing
(id/title/location/isRemote/workplaceType/descriptionPlain/publishedAt/
jobUrl/applyUrl). Parsing is defensive (.get with fallbacks) so a minor
field-name drift on Ashby's side degrades a single job rather than crashing
the whole fetch.
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from jobapply import config
from jobapply.sources.base import RawJob, humanize_token

logger = logging.getLogger(__name__)

JOB_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{board_name}"

_WORKPLACE_TYPE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
}


class AshbySource:
    name = "ashby"

    def fetch(self) -> list[RawJob]:
        if not config.get_bool("sources.ashby.enabled"):
            return []
        jobs: list[RawJob] = []
        for board_name in config.get_list("sources.ashby.boards"):
            try:
                jobs.extend(self._fetch_board(board_name))
            except httpx.HTTPError as exc:
                logger.warning("ashby: failed to fetch board %r: %s", board_name, exc)
        return jobs

    def _fetch_board(self, board_name: str) -> list[RawJob]:
        response = httpx.get(
            JOB_BOARD_URL.format(board_name=board_name),
            params={"includeCompensation": "true"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        company = humanize_token(board_name)
        results: list[RawJob] = []
        for job in payload.get("jobs", []):
            remote_type = _remote_type(job)
            results.append(
                RawJob(
                    source=self.name,
                    external_id=str(job.get("id") or job.get("jobId") or job.get("title")),
                    company=company,
                    title=job.get("title", ""),
                    location=job.get("location"),
                    remote_type=remote_type,
                    url=job.get("jobUrl") or job.get("applyUrl") or "",
                    description_raw=job.get("descriptionPlain") or job.get("descriptionHtml"),
                    posted_at=_parse_iso(job.get("publishedAt")),
                    raw=job,
                )
            )
        return results


def _remote_type(job: dict) -> str:
    workplace_type = (job.get("workplaceType") or "").lower()
    if workplace_type in _WORKPLACE_TYPE_MAP:
        return _WORKPLACE_TYPE_MAP[workplace_type]
    if job.get("isRemote"):
        return "remote"
    return "unknown"


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None
