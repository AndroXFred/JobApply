from __future__ import annotations

from sqlalchemy import select

from jobapply.agents import applier
from jobapply.applier.platforms.base import ApplyOutcome
from jobapply.db.models import Application, Job, StatusHistory, TailoredResume
from jobapply.db.session import session_scope
from jobapply.resume.schema import ContactInfo, ResumeDocument

MASTER = ResumeDocument(
    contact=ContactInfo(first_name="Jane", last_name="Doe", email="jane@example.com", phone="+1 555 123 4567"),
    summary="Senior engineer.",
)


def _seed_approved_job(url: str, with_tailored_resume: bool = True) -> int:
    with session_scope() as session:
        job = Job(
            source="greenhouse",
            external_id="1",
            company="Acme",
            title="Engineer",
            url=url,
            status="approved",
            raw_json={},
        )
        session.add(job)
        session.flush()
        if with_tailored_resume:
            session.add(
                TailoredResume(
                    job_id=job.id,
                    structured_json={},
                    pdf_path="/tmp/fake_resume.pdf",
                    fabrication_check_passed=True,
                    fabrication_check_notes="",
                    llm_model="fake-model",
                )
            )
        return job.id


def test_run_applier_success_marks_applied(temp_db, monkeypatch):
    job_id = _seed_approved_job("https://boards.greenhouse.io/acme/jobs/1")
    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)

    outcome = ApplyOutcome(status="submitted", confirmation_text="Thanks for applying!", screenshot_path="/tmp/shot.png")
    monkeypatch.setattr(applier.playwright_runner, "run_application", lambda *a, **k: outcome)

    stats = applier.run_applier()
    assert stats == {"processed": 1, "applied": 1, "unsupported": 0, "failed": 0}

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "applied"
        app = session.scalar(select(Application).where(Application.job_id == job_id))
        assert app.status == "submitted"
        assert app.ats_platform == "greenhouse"
        assert app.confirmation_text == "Thanks for applying!"
        assert app.confirmation_screenshot_path == "/tmp/shot.png"
        assert app.submitted_at is not None
        history_to = [h.to_status for h in session.scalars(select(StatusHistory).where(StatusHistory.job_id == job_id))]
        assert history_to == ["applying", "applied"]


def test_run_applier_bails_on_unmappable_fields(temp_db, monkeypatch):
    job_id = _seed_approved_job("https://jobs.lever.co/acme/1")
    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)

    outcome = ApplyOutcome(status="unmappable_fields", unmapped_fields=["Why do you want to work here?"], screenshot_path="/tmp/shot.png")
    monkeypatch.setattr(applier.playwright_runner, "run_application", lambda *a, **k: outcome)

    stats = applier.run_applier()
    assert stats["failed"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "apply_failed"
        app = session.scalar(select(Application).where(Application.job_id == job_id))
        assert app.status == "failed"
        assert "Why do you want to work here?" in app.error_message


def test_run_applier_skips_unsupported_platform_without_calling_playwright(temp_db, monkeypatch):
    job_id = _seed_approved_job("https://example.com/careers/some-job")
    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)

    def _fail(*a, **k):
        raise AssertionError("playwright should never be invoked for an unsupported platform")

    monkeypatch.setattr(applier.playwright_runner, "run_application", _fail)

    stats = applier.run_applier()
    assert stats["unsupported"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "apply_failed"
        app = session.scalar(select(Application).where(Application.job_id == job_id))
        assert app.ats_platform == "unsupported"


def test_run_applier_fails_gracefully_when_no_tailored_resume(temp_db, monkeypatch):
    job_id = _seed_approved_job("https://boards.greenhouse.io/acme/jobs/1", with_tailored_resume=False)
    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)

    def _fail(*a, **k):
        raise AssertionError("playwright should never be invoked without a tailored resume")

    monkeypatch.setattr(applier.playwright_runner, "run_application", _fail)

    stats = applier.run_applier()
    assert stats["unsupported"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "apply_failed"


def test_run_applier_marks_failed_on_unexpected_exception(temp_db, monkeypatch):
    job_id = _seed_approved_job("https://jobs.ashbyhq.com/acme/1")
    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)

    def _raise(*a, **k):
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(applier.playwright_runner, "run_application", _raise)

    stats = applier.run_applier()
    assert stats["failed"] == 1

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "apply_failed"
        app = session.scalar(select(Application).where(Application.job_id == job_id))
        assert "browser crashed" in app.error_message


def test_run_applier_scoped_to_single_job_id(temp_db, monkeypatch):
    job_id_1 = _seed_approved_job("https://boards.greenhouse.io/acme/jobs/1")
    with session_scope() as session:
        job2 = Job(source="lever", external_id="2", company="Other", title="Eng", url="https://jobs.lever.co/other/2", status="approved", raw_json={})
        session.add(job2)
        session.flush()
        job_id_2 = job2.id

    monkeypatch.setattr(applier, "load_master_resume", lambda: MASTER)
    monkeypatch.setattr(
        applier.playwright_runner,
        "run_application",
        lambda *a, **k: ApplyOutcome(status="submitted", confirmation_text="ok"),
    )

    stats = applier.run_applier(job_id=job_id_1)
    assert stats["processed"] == 1

    with session_scope() as session:
        assert session.get(Job, job_id_1).status == "applied"
        assert session.get(Job, job_id_2).status == "approved"  # untouched
