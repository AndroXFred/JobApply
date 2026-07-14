from __future__ import annotations

from sqlalchemy import select

from jobapply.db.models import PipelineRun
from jobapply.db.session import session_scope
from jobapply.web import scheduler


def test_run_pipeline_job_records_success_for_all_stages(temp_db, monkeypatch):
    monkeypatch.setattr(scheduler, "run_finder", lambda: {"found": 1, "new": 1})
    monkeypatch.setattr(scheduler, "run_tailor", lambda: {"processed": 1, "tailored": 1})
    monkeypatch.setattr(scheduler, "run_applier", lambda: {"processed": 0, "applied": 0})

    result = scheduler.run_pipeline_job(trigger_source="manual")
    assert result["finder"] == {"found": 1, "new": 1}

    with session_scope() as session:
        run = session.scalar(select(PipelineRun))
        assert run.trigger == "manual"
        assert run.finished_at is not None
        assert run.finder_stats == {"found": 1, "new": 1}
        assert run.finder_error is None
        assert run.tailor_stats == {"processed": 1, "tailored": 1}
        assert run.applier_stats == {"processed": 0, "applied": 0}


def test_run_pipeline_job_records_per_stage_errors_without_crashing(temp_db, monkeypatch):
    def _broken():
        raise RuntimeError("resume file not found")

    monkeypatch.setattr(scheduler, "run_finder", _broken)
    monkeypatch.setattr(scheduler, "run_tailor", lambda: {"processed": 0})
    monkeypatch.setattr(scheduler, "run_applier", lambda: {"processed": 0})

    result = scheduler.run_pipeline_job(trigger_source="cron")
    assert result["finder"] is None
    assert result["tailor"] == {"processed": 0}

    with session_scope() as session:
        run = session.scalar(select(PipelineRun))
        assert run.finder_stats is None
        assert "resume file not found" in run.finder_error
        assert run.tailor_error is None
