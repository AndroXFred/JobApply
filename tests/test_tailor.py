from __future__ import annotations

from sqlalchemy import select

from jobapply import config
from jobapply.agents import tailor
from jobapply.db.models import Approval, Job, StatusHistory, TailoredResume
from jobapply.db.session import session_scope
from jobapply.llm.schemas import ClaimVerdict, FabricationCheckResult
from jobapply.resume.schema import ContactInfo, ExperienceEntry, ResumeDocument

MASTER = ResumeDocument(
    contact=ContactInfo(first_name="Test", last_name="Person", email="t@example.com", phone="+1 555 555 5555"),
    summary="Senior backend engineer with 8 years of Python experience.",
    skills=["Python", "FastAPI", "PostgreSQL"],
    experience=[
        ExperienceEntry(
            company="Acme",
            title="Senior Engineer",
            start_date="2020-01",
            end_date="present",
            bullets=["Led a team of 4 engineers.", "Reduced latency by 30%."],
        )
    ],
)


def _seed_pending_tailor_job(company="Acme Target", title="Backend Engineer") -> int:
    with session_scope() as session:
        job = Job(
            source="greenhouse",
            external_id="1",
            company=company,
            title=title,
            url="https://example.com/1",
            description_raw="Build backend systems.",
            status="pending_tailor",
            raw_json={},
        )
        session.add(job)
        session.flush()
        return job.id


class _FakeTailorClient:
    def __init__(self, tailored: ResumeDocument):
        self._tailored = tailored

    def complete_json(self, *, system, user, response_schema, model):
        return self._tailored


class _FakeAuditClient:
    def __init__(self, result: FabricationCheckResult):
        self._result = result

    def complete_json(self, *, system, user, response_schema, model):
        return self._result


def _patch_clients(monkeypatch, tailored: ResumeDocument, audit: FabricationCheckResult):
    monkeypatch.setattr(tailor, "load_master_resume", lambda: MASTER)
    monkeypatch.setattr(
        tailor,
        "get_client_for",
        lambda agent: (_FakeTailorClient(tailored), "fake-tailor-model")
        if agent == "tailor"
        else (_FakeAuditClient(audit), "fake-audit-model"),
    )


def test_run_tailor_success_creates_pdf_and_approval_and_notifies(temp_db, monkeypatch):
    job_id = _seed_pending_tailor_job()
    config.set_setting("notify.ntfy.topic", "test-topic")

    tailored = MASTER.model_copy(deep=True)
    audit = FabricationCheckResult(
        claims=[ClaimVerdict(claim="Led a team of 4 engineers.", verdict="supported", master_source_ref="Acme bullet")]
    )
    _patch_clients(monkeypatch, tailored, audit)

    published = []
    monkeypatch.setattr(tailor.ntfy, "publish", lambda job, fit_score=None: published.append((job.id, fit_score)))

    stats = tailor.run_tailor()

    assert stats == {"processed": 1, "tailored": 1, "blocked": 0, "failed": 0}
    assert published == [(job_id, None)]

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "pending_approval"

        tr = session.scalar(select(TailoredResume).where(TailoredResume.job_id == job_id))
        assert tr.fabrication_check_passed is True
        assert tr.pdf_path.endswith(f"job_{job_id}.pdf")

        approval = session.scalar(select(Approval).where(Approval.job_id == job_id))
        assert approval.decision == "pending"

        history_notes = [h.to_status for h in session.scalars(select(StatusHistory)).all()]
        assert "pending_approval" in history_notes


def test_run_tailor_blocks_on_unsupported_claim(temp_db, monkeypatch):
    job_id = _seed_pending_tailor_job()

    tailored = MASTER.model_copy(deep=True)
    tailored.experience[0].bullets.append("Increased revenue by $5,000,000.")  # fabricated, not in master
    audit = FabricationCheckResult(
        claims=[
            ClaimVerdict(claim="Led a team of 4 engineers.", verdict="supported", master_source_ref="Acme bullet"),
            ClaimVerdict(claim="Increased revenue by $5,000,000.", verdict="unsupported", master_source_ref=None),
        ]
    )
    _patch_clients(monkeypatch, tailored, audit)
    monkeypatch.setattr(tailor.ntfy, "publish", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not notify")))

    stats = tailor.run_tailor()

    # the fabricated dollar figure trips the deterministic numeric pre-check
    # before the LLM audit even runs, so this is a "blocked" outcome either way
    assert stats["tailored"] == 0
    assert stats["blocked"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "tailoring_failed"
        tr = session.scalar(select(TailoredResume).where(TailoredResume.job_id == job_id))
        assert tr.fabrication_check_passed is False
        assert tr.pdf_path == ""


def test_run_tailor_numeric_precheck_blocks_before_llm_audit(temp_db, monkeypatch):
    job_id = _seed_pending_tailor_job()

    tailored = MASTER.model_copy(deep=True)
    tailored.summary = "Senior backend engineer with 15 years of Python experience."  # master says 8

    monkeypatch.setattr(tailor, "load_master_resume", lambda: MASTER)
    monkeypatch.setattr(tailor, "get_client_for", lambda agent: (_FakeTailorClient(tailored), "fake-model"))

    def _fail_audit(*args, **kwargs):
        raise AssertionError("audit LLM should not be called when the numeric pre-check fails")

    monkeypatch.setattr(tailor, "_audit_resume", _fail_audit)

    stats = tailor.run_tailor(job_id=job_id)
    assert stats["blocked"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "tailoring_failed"


def test_run_tailor_marks_failed_on_llm_error(temp_db, monkeypatch):
    job_id = _seed_pending_tailor_job()
    monkeypatch.setattr(tailor, "load_master_resume", lambda: MASTER)

    class _BrokenClient:
        def complete_json(self, **kwargs):
            raise RuntimeError("LLM down")

    monkeypatch.setattr(tailor, "get_client_for", lambda agent: (_BrokenClient(), "fake-model"))

    stats = tailor.run_tailor(job_id=job_id)
    assert stats["failed"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "tailoring_failed"
