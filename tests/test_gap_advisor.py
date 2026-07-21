from __future__ import annotations

from sqlalchemy import select

from jobapply.agents import gap_advisor
from jobapply.db.models import Evaluation, GapReport, Job
from jobapply.db.session import session_scope
from jobapply.llm.schemas import GapRecommendation, GapRecommendationResult
from jobapply.resume.schema import ContactInfo, ResumeDocument

MASTER = ResumeDocument(
    contact=ContactInfo(first_name="Jane", last_name="Doe", email="jane@example.com"),
    summary="Senior backend engineer.",
    skills=["Python", "FastAPI"],
)


def _seed_evaluation(company: str, title: str, key_requirements: list[str]) -> None:
    with session_scope() as session:
        job = Job(source="greenhouse", external_id=company + title, company=company, title=title, url="https://x", raw_json={})
        session.add(job)
        session.flush()
        session.add(
            Evaluation(
                job_id=job.id,
                fit_score=80,
                rationale="r",
                red_flags=[],
                recommendation="pursue",
                key_requirements=key_requirements,
                llm_model="fake",
                prompt_version="2",
            )
        )


class _FakeClient:
    def __init__(self, result: GapRecommendationResult):
        self._result = result

    def complete_json(self, *, system, user, response_schema, model):
        return self._result


def test_run_gap_analysis_with_no_evaluations_reports_zero(temp_db, monkeypatch):
    monkeypatch.setattr(gap_advisor, "load_master_resume", lambda: MASTER)

    stats = gap_advisor.run_gap_analysis(trigger="manual")
    assert stats == {"jobs_analyzed": 0, "gaps_found": 0}

    with session_scope() as session:
        report = session.scalar(select(GapReport))
        assert report.jobs_analyzed_count == 0
        assert report.gaps == []
        assert report.error is None


def test_run_gap_analysis_filters_out_skills_already_in_resume(temp_db, monkeypatch):
    monkeypatch.setattr(gap_advisor, "load_master_resume", lambda: MASTER)
    _seed_evaluation("Acme", "Backend Engineer", ["Python", "FastAPI"])  # both already in resume

    stats = gap_advisor.run_gap_analysis(trigger="manual")
    assert stats == {"jobs_analyzed": 1, "gaps_found": 0}


def test_run_gap_analysis_surfaces_gaps_with_recommendations(temp_db, monkeypatch):
    monkeypatch.setattr(gap_advisor, "load_master_resume", lambda: MASTER)
    _seed_evaluation("Acme", "Backend Engineer", ["Kubernetes", "Python"])
    _seed_evaluation("Other Co", "Platform Engineer", ["Kubernetes", "AWS"])

    recommendation = GapRecommendationResult(
        recommendations=[
            GapRecommendation(
                skill="Kubernetes",
                summary="Shows up a lot.",
                certifications=["Certified Kubernetes Administrator (CKA)"],
                courses=["freeCodeCamp Kubernetes course"],
                priority="high",
            ),
            GapRecommendation(
                skill="AWS", summary="Common too.", certifications=[], courses=[], priority="medium"
            ),
        ]
    )
    monkeypatch.setattr(gap_advisor, "get_client_for", lambda agent: (_FakeClient(recommendation), "fake-model"))

    stats = gap_advisor.run_gap_analysis(trigger="cron")
    assert stats == {"jobs_analyzed": 2, "gaps_found": 2}

    with session_scope() as session:
        report = session.scalar(select(GapReport))
        assert report.llm_model == "fake-model"
        gaps_by_skill = {g["skill"]: g for g in report.gaps}
        assert gaps_by_skill["Kubernetes"]["frequency"] == 2
        assert gaps_by_skill["Kubernetes"]["recommendation"]["priority"] == "high"
        assert "Certified Kubernetes Administrator (CKA)" in gaps_by_skill["Kubernetes"]["recommendation"]["certifications"]
        assert gaps_by_skill["AWS"]["frequency"] == 1
        assert gaps_by_skill["AWS"]["recommendation"]["priority"] == "medium"


def test_run_gap_analysis_handles_recommendation_name_mismatch_gracefully(temp_db, monkeypatch):
    monkeypatch.setattr(gap_advisor, "load_master_resume", lambda: MASTER)
    _seed_evaluation("Acme", "Backend Engineer", ["Kubernetes"])

    # LLM echoes back a slightly different phrasing than the input skill string
    recommendation = GapRecommendationResult(
        recommendations=[
            GapRecommendation(skill="kubernetes (k8s)", summary="x", certifications=[], courses=[], priority="low")
        ]
    )
    monkeypatch.setattr(gap_advisor, "get_client_for", lambda agent: (_FakeClient(recommendation), "fake-model"))

    stats = gap_advisor.run_gap_analysis()
    assert stats["gaps_found"] == 1

    with session_scope() as session:
        report = session.scalar(select(GapReport))
        assert report.gaps[0]["recommendation"] is not None  # substring match still found it


def test_run_gap_analysis_preserves_jobs_analyzed_count_when_llm_call_fails(temp_db, monkeypatch):
    monkeypatch.setattr(gap_advisor, "load_master_resume", lambda: MASTER)
    _seed_evaluation("Acme", "Backend Engineer", ["Kubernetes"])
    _seed_evaluation("Other Co", "Platform Engineer", ["Kubernetes"])

    def _broken_client(agent):
        raise RuntimeError("LLM is down")

    monkeypatch.setattr(gap_advisor, "get_client_for", _broken_client)

    stats = gap_advisor.run_gap_analysis(trigger="cron")
    assert stats["error"] is not None
    # aggregation succeeded (2 evaluations) before the LLM call failed -
    # that shouldn't be lost just because the later step errored
    assert stats["jobs_analyzed"] == 2

    with session_scope() as session:
        report = session.scalar(select(GapReport))
        assert report.jobs_analyzed_count == 2


def test_run_gap_analysis_records_error_on_failure(temp_db, monkeypatch):
    def _broken():
        raise FileNotFoundError("Master resume not found")

    monkeypatch.setattr(gap_advisor, "load_master_resume", _broken)

    stats = gap_advisor.run_gap_analysis(trigger="cron")
    assert stats["error"] is not None
    assert "Master resume not found" in stats["error"]

    with session_scope() as session:
        report = session.scalar(select(GapReport))
        assert report.error is not None
        assert report.jobs_analyzed_count == 0
