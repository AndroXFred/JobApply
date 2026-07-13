"""Greenhouse public job board API. No auth, no scraping.

https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from jobapply import config
from jobapply.sources.base import RawJob, humanize_token

logger = logging.getLogger(__name__)

BOARD_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _infer_remote_type(location: str | None) -> str:
    if not location:
        return "unknown"
    return "remote" if "remote" in location.lower() else "unknown"


class GreenhouseSource:
    name = "greenhouse"

    def fetch(self) -> list[RawJob]:
        if not config.get_bool("sources.greenhouse.enabled"):
            return []
        jobs: list[RawJob] = []
        for token in config.get_list("sources.greenhouse.boards"):
            try:
                jobs.extend(self._fetch_board(token))
            except httpx.HTTPError as exc:
                logger.warning("greenhouse: failed to fetch board %r: %s", token, exc)
        return jobs

    def _fetch_board(self, token: str) -> list[RawJob]:
        response = httpx.get(
            BOARD_JOBS_URL.format(token=token), params={"content": "true"}, timeout=30.0
        )
        response.raise_for_status()
        payload = response.json()
        company = humanize_token(token)
        results: list[RawJob] = []
        for job in payload.get("jobs", []):
            location = (job.get("location") or {}).get("name")
            updated_at = job.get("updated_at")
            posted_at = _parse_iso(updated_at)
            results.append(
                RawJob(
                    source=self.name,
                    external_id=str(job.get("id")),
                    company=company,
                    title=job.get("title", ""),
                    location=location,
                    remote_type=_infer_remote_type(location),
                    url=job.get("absolute_url", ""),
                    description_raw=job.get("content"),
                    posted_at=posted_at,
                    raw=job,
                )
            )
        return results


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None
