"""Lever public postings API. No auth, no scraping.

https://api.lever.co/v0/postings/{site}?mode=json
"""

from __future__ import annotations

import logging

import httpx

from jobapply import config
from jobapply.sources.base import RawJob, humanize_token

logger = logging.getLogger(__name__)

POSTINGS_URL = "https://api.lever.co/v0/postings/{site}"

_REMOTE_TYPE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on-site": "onsite",
    "unspecified": "unknown",
}


class LeverSource:
    name = "lever"

    def fetch(self) -> list[RawJob]:
        if not config.get_bool("sources.lever.enabled"):
            return []
        jobs: list[RawJob] = []
        for site in config.get_list("sources.lever.boards"):
            try:
                jobs.extend(self._fetch_site(site))
            except httpx.HTTPError as exc:
                logger.warning("lever: failed to fetch site %r: %s", site, exc)
        return jobs

    def _fetch_site(self, site: str) -> list[RawJob]:
        response = httpx.get(POSTINGS_URL.format(site=site), params={"mode": "json"}, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        company = humanize_token(site)
        results: list[RawJob] = []
        for job in payload:
            categories = job.get("categories") or {}
            location = categories.get("location")
            salary_range = job.get("salaryRange") or {}
            salary_min = salary_range.get("min")
            salary_max = salary_range.get("max")
            results.append(
                RawJob(
                    source=self.name,
                    external_id=str(job.get("id")),
                    company=company,
                    title=job.get("text", ""),
                    location=location,
                    remote_type=_REMOTE_TYPE_MAP.get(job.get("workplaceType", ""), "unknown"),
                    url=job.get("hostedUrl", ""),
                    description_raw=job.get("descriptionPlain") or job.get("description"),
                    salary_min=int(salary_min) if salary_min is not None else None,
                    salary_max=int(salary_max) if salary_max is not None else None,
                    raw=job,
                )
            )
        return results
