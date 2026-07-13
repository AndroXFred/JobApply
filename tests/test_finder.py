from __future__ import annotations

from sqlalchemy import select

from jobapply.agents import finder
from jobapply.db.models import Evaluation, Job, StatusHistory
from jobapply.db.session import session_scope
from jobapply.llm.schemas import JobEvaluation
from jobapply.sources.base import RawJob


def _raw_job(**overrides) -> RawJob:
    defaults = dict(
        source="greenhouse",
        external_id="123",
        company="Acme Corp",
        title="Senior Backend Engineer",
        location="Remote",
        remote_type="remote",
        url="https://example.com/jobs/123",
        description_raw="Build things with Python.",
    )
    defaults.update(overrides)
    return RawJob(**defaults)


def test_upsert_job_hard_dedupe_by_source_and_external_id(temp_db):
    raw = _raw_job()
    with session_scope() as session:
        job_id_1, is_new_1 = finder._upsert_job(session, raw)
    with session_scope() as session:
        job_id_2, is_new_2 = finder._upsert_job(session, raw)

    assert is_new_1 is True
    assert is_new_2 is False
    assert job_id_1 == job_id_2
    with session_scope() as session:
        assert session.scalar(select(Job).where(Job.id == job_id_1)) is not None
        count = len(session.scalars(select(Job)).all())
    assert count == 1


def test_upsert_job_soft_dedupe_across_sources_is_surfaced_not_dropped(temp_db):
    raw_a = _raw_job(source="greenhouse", external_id="1")
    raw_b = _raw_job(source="lever", external_id="2")  # same company/title/remote_type

    with session_scope() as session:
        job_id_a, _ = finder._upsert_job(session, raw_a)
    with session_scope() as session:
        job_id_b, is_new_b = finder._upsert_job(session, raw_b)

    assert is_new_b is True
    assert job_id_a != job_id_b
    with session_scope() as session:
        job_b = session.get(Job, job_id_b)
        assert job_b.duplicate_of_job_id == job_id_a
        # both rows still present - soft dedupe surfaces, doesn't drop
        assert len(session.scalars(select(Job)).all()) == 2


class _FakeSource:
    name = "fake"

    def __init__(self, jobs: list[RawJob]):
        self._jobs = jobs

    def fetch(self) -> list[RawJob]:
        return self._jobs


class _FakeClient:
    def __init__(self, canned: dict[str, JobEvaluation]):
        self._canned = canned

    def complete_json(self, *, system, user, response_schema, model):
        for title, evaluation in self._canned.items():
            if title in user:
                return evaluation
        raise AssertionError("no canned evaluation matched the prompt")


def test_run_finder_persists_pursue_and_rejected_jobs(temp_db, monkeypatch):
    good_job = _raw_job(external_id="good", title="Senior Python Engineer")
    bad_job = _raw_job(external_id="bad", title="Junior Marketing Intern")

    monkeypatch.setattr(finder, "ALL_SOURCES", [_FakeSource([good_job, bad_job])])
    monkeypatch.setattr(finder, "load_master_resume_text", lambda: "Senior Python engineer, 8 years experience.")

    canned = {
        "Senior Python Engineer": JobEvaluation(
            fit_score=90, rationale="Strong match.", red_flags=[], recommendation="pursue"
        ),
        "Junior Marketing Intern": JobEvaluation(
            fit_score=10, rationale="Not a fit.", red_flags=["seniority_mismatch"], recommendation="reject"
        ),
    }
    fake_client = _FakeClient(canned)
    monkeypatch.setattr(finder, "get_client_for", lambda agent: (fake_client, "fake-model"))

    stats = finder.run_finder()

    assert stats == {"found": 2, "new": 2, "evaluated": 2, "pursue": 1, "rejected": 1, "failed": 0}

    with session_scope() as session:
        jobs = {j.title: j for j in session.scalars(select(Job)).all()}
        assert jobs["Senior Python Engineer"].status == "pending_tailor"
        assert jobs["Junior Marketing Intern"].status == "rejected"

        evals = session.scalars(select(Evaluation)).all()
        assert {e.fit_score for e in evals} == {90, 10}

        history = session.scalars(select(StatusHistory)).all()
        # each job: new -> (pending_tailor | rejected)
        assert len(history) == 4


def test_run_finder_marks_evaluation_failed_on_llm_error(temp_db, monkeypatch):
    raw = _raw_job(external_id="err", title="Whatever Role")
    monkeypatch.setattr(finder, "ALL_SOURCES", [_FakeSource([raw])])
    monkeypatch.setattr(finder, "load_master_resume_text", lambda: "resume text")

    class _BrokenClient:
        def complete_json(self, **kwargs):
            raise RuntimeError("LLM is down")

    monkeypatch.setattr(finder, "get_client_for", lambda agent: (_BrokenClient(), "fake-model"))

    stats = finder.run_finder()
    assert stats["failed"] == 1
    assert stats["evaluated"] == 0

    with session_scope() as session:
        job = session.scalar(select(Job))
        assert job.status == "evaluation_failed"
