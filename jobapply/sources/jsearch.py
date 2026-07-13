"""JSearch via RapidAPI — aggregates LinkedIn/Indeed/Glassdoor/ZipRecruiter
under a paid, ToS-legitimate API (not scraping).

https://jsearch.p.rapidapi.com/search
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from jobapply import config
from jobapply.sources.base import RawJob

logger = logging.getLogger(__name__)

SEARCH_URL = "https://{host}/search"


class JSearchSource:
    name = "jsearch"

    def fetch(self) -> list[RawJob]:
        if not config.get_bool("sources.jsearch.enabled"):
            return []
        api_key = config.get_setting("sources.jsearch.api_key")
        if not api_key:
            logger.warning("jsearch: enabled but no api key configured, skipping")
            return []

        host = config.get_setting("sources.jsearch.host") or "jsearch.p.rapidapi.com"
        params = {
            "query": self._query(),
            "page": "1",
            "num_pages": "1",
            "date_posted": config.get_setting("sources.jsearch.date_posted") or "week",
            "remote_jobs_only": "true" if config.get_bool("sources.jsearch.remote_jobs_only") else "false",
        }
        try:
            response = httpx.get(
                SEARCH_URL.format(host=host),
                params=params,
                headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": host},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("jsearch: request failed: %s", exc)
            return []

        payload = response.json()
        return [self._to_raw_job(job) for job in payload.get("data", [])]

    def _query(self) -> str:
        query = config.get_setting("sources.jsearch.query") or "software engineer remote"
        location = config.get_setting("sources.jsearch.location")
        return f"{query} in {location}" if location else query

    def _to_raw_job(self, job: dict) -> RawJob:
        location_parts = [job.get("job_city"), job.get("job_state"), job.get("job_country")]
        location = ", ".join(p for p in location_parts if p) or None
        return RawJob(
            source=self.name,
            external_id=str(job.get("job_id")),
            company=job.get("employer_name") or "Unknown",
            title=job.get("job_title", ""),
            location=location,
            remote_type="remote" if job.get("job_is_remote") else "unknown",
            url=job.get("job_apply_link") or "",
            description_raw=job.get("job_description"),
            salary_min=_to_int(job.get("job_min_salary")),
            salary_max=_to_int(job.get("job_max_salary")),
            posted_at=_parse_iso(job.get("job_posted_at_datetime_utc")),
            raw=job,
        )


def _to_int(value) -> int | None:
    return int(value) if value is not None else None


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
