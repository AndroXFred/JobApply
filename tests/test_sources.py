from __future__ import annotations

import httpx

from jobapply import config
from jobapply.sources.ashby import AshbySource
from jobapply.sources.greenhouse import GreenhouseSource
from jobapply.sources.jsearch import JSearchSource
from jobapply.sources.lever import LeverSource


def _fake_get(payload: dict | list, status_code: int = 200):
    def _get(url, params=None, headers=None, timeout=None):
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return _get


def test_greenhouse_parses_jobs(temp_db, monkeypatch):
    config.set_setting("sources.greenhouse.enabled", "true")
    config.set_setting("sources.greenhouse.boards", "acme-corp")
    payload = {
        "jobs": [
            {
                "id": 111,
                "title": "Staff Engineer",
                "location": {"name": "Remote - US"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/111",
                "content": "<p>Job details</p>",
                "updated_at": "2026-07-01T12:00:00-00:00",
            }
        ]
    }
    monkeypatch.setattr("jobapply.sources.greenhouse.httpx.get", _fake_get(payload))

    jobs = GreenhouseSource().fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "greenhouse"
    assert job.external_id == "111"
    assert job.company == "Acme Corp"
    assert job.remote_type == "remote"
    assert job.url.endswith("/111")


def test_greenhouse_disabled_returns_empty(temp_db, monkeypatch):
    config.set_setting("sources.greenhouse.enabled", "false")
    config.set_setting("sources.greenhouse.boards", "acme-corp")
    monkeypatch.setattr("jobapply.sources.greenhouse.httpx.get", _fake_get({"jobs": []}))
    assert GreenhouseSource().fetch() == []


def test_lever_parses_jobs(temp_db, monkeypatch):
    config.set_setting("sources.lever.enabled", "true")
    config.set_setting("sources.lever.boards", "examplecorp")
    payload = [
        {
            "id": "abc-123",
            "text": "Backend Engineer",
            "categories": {"location": "Remote"},
            "workplaceType": "remote",
            "hostedUrl": "https://jobs.lever.co/examplecorp/abc-123",
            "descriptionPlain": "Do backend things.",
            "salaryRange": {"min": 120000, "max": 160000},
        }
    ]
    monkeypatch.setattr("jobapply.sources.lever.httpx.get", _fake_get(payload))

    jobs = LeverSource().fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "abc-123"
    assert job.remote_type == "remote"
    assert job.salary_min == 120000
    assert job.salary_max == 160000


def test_ashby_parses_jobs_defensively(temp_db, monkeypatch):
    config.set_setting("sources.ashby.enabled", "true")
    config.set_setting("sources.ashby.boards", "examplecorp")
    payload = {
        "jobs": [
            {
                "id": "job-1",
                "title": "Platform Engineer",
                "location": "Remote",
                "isRemote": True,
                "workplaceType": "Remote",
                "descriptionPlain": "Platform work.",
                "publishedAt": "2026-06-01T00:00:00.000+00:00",
                "jobUrl": "https://jobs.ashbyhq.com/examplecorp/job-1",
            }
        ]
    }
    monkeypatch.setattr("jobapply.sources.ashby.httpx.get", _fake_get(payload))

    jobs = AshbySource().fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.remote_type == "remote"
    assert job.external_id == "job-1"


def test_jsearch_skips_when_no_api_key(temp_db):
    config.set_setting("sources.jsearch.enabled", "true")
    config.set_setting("sources.jsearch.api_key", None)
    assert JSearchSource().fetch() == []


def test_jsearch_parses_jobs(temp_db, monkeypatch):
    config.set_setting("sources.jsearch.enabled", "true")
    config.set_setting("sources.jsearch.api_key", "fake-key")
    payload = {
        "data": [
            {
                "job_id": "j1",
                "job_title": "Remote Data Engineer",
                "employer_name": "DataCo",
                "job_city": "Austin",
                "job_state": "TX",
                "job_country": "US",
                "job_is_remote": True,
                "job_apply_link": "https://example.com/apply/j1",
                "job_description": "Data things.",
                "job_min_salary": 100000,
                "job_max_salary": 140000,
                "job_posted_at_datetime_utc": "2026-07-01T00:00:00.000Z",
            }
        ]
    }
    monkeypatch.setattr("jobapply.sources.jsearch.httpx.get", _fake_get(payload))

    jobs = JSearchSource().fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "DataCo"
    assert job.remote_type == "remote"
    assert job.location == "Austin, TX, US"
