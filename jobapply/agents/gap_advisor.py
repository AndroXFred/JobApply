"""Gap Advisor: mines job postings/evaluations already collected to surface
recurring skill/qualification gaps between the master resume and what
employers actually ask for.

Strictly advisory - never writes to the master resume. Deep-scanning is
"free": Agent 1 already extracts key_requirements from each posting's full
description as part of its normal evaluation call (see agents/finder.py),
so this agent does pure-Python aggregation over already-collected data and
spends exactly one LLM call per report, for recommendations only.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from jobapply.db.models import Evaluation, GapReport, Job
from jobapply.db.session import session_scope
from jobapply.llm.client import get_client_for
from jobapply.llm.schemas import GapRecommendation, GapRecommendationResult
from jobapply.resume.loader import load_master_resume
from jobapply.resume.schema import resume_text_blob

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "gap_advisor_system.md"
_LOOKBACK_EVALUATIONS = 200  # bounds aggregation size and the recommendation prompt
_TOP_N_GAPS = 15


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _aggregate_gaps(session, resume_text: str) -> tuple[list[dict], int]:
    evaluations = session.scalars(
        select(Evaluation).order_by(Evaluation.created_at.desc()).limit(_LOOKBACK_EVALUATIONS)
    ).all()

    counts: Counter[str] = Counter()
    display_name: dict[str, str] = {}
    example_job: dict[str, tuple[str, str]] = {}

    for evaluation in evaluations:
        job = session.get(Job, evaluation.job_id)
        for raw_skill in evaluation.key_requirements or []:
            normalized = raw_skill.strip().lower()
            if not normalized:
                continue
            counts[normalized] += 1
            display_name.setdefault(normalized, raw_skill.strip())
            example_job.setdefault(normalized, (job.company, job.title) if job else ("", ""))

    gaps = [
        {
            "skill": display_name[normalized],
            "frequency": freq,
            "example_jobs": [{"company": example_job[normalized][0], "title": example_job[normalized][1]}],
        }
        for normalized, freq in counts.most_common()
        if normalized not in resume_text
    ][:_TOP_N_GAPS]

    return gaps, len(evaluations)


def _match_recommendation(skill: str, by_skill: dict[str, GapRecommendation]) -> GapRecommendation | None:
    normalized = skill.strip().lower()
    if normalized in by_skill:
        return by_skill[normalized]
    for key, rec in by_skill.items():
        if normalized in key or key in normalized:
            return rec
    return None


def run_gap_analysis(trigger: str = "manual") -> dict[str, int | str | None]:
    """Single try/except around the whole run: any failure (missing resume,
    LLM error, ...) still lands a GapReport row with `error` set, so it's
    visible on the /gaps dashboard instead of only in the server log - the
    same lesson learned from the main pipeline's silent-failure gap."""
    jobs_analyzed_count = 0
    try:
        master = load_master_resume()
        resume_text = resume_text_blob(master).lower()

        with session_scope() as session:
            gaps, jobs_analyzed_count = _aggregate_gaps(session, resume_text)

        llm_model = None
        if gaps:
            client, model = get_client_for("gap_advisor")
            user_prompt = (
                f"## Candidate's master resume\n{master.model_dump_json(indent=2)}\n\n"
                f"## Recurring gaps across {jobs_analyzed_count} recently evaluated postings\n"
                + "\n".join(
                    f"- {g['skill']} (seen in {g['frequency']} postings, e.g. {g['example_jobs'][0]['title']} at "
                    f"{g['example_jobs'][0]['company']})"
                    for g in gaps
                )
            )
            result = client.complete_json(
                system=_system_prompt(), user=user_prompt, response_schema=GapRecommendationResult, model=model
            )
            by_skill = {r.skill.strip().lower(): r for r in result.recommendations}

            for gap in gaps:
                rec = _match_recommendation(gap["skill"], by_skill)
                gap["recommendation"] = (
                    {
                        "summary": rec.summary,
                        "certifications": rec.certifications,
                        "courses": rec.courses,
                        "priority": rec.priority,
                    }
                    if rec
                    else None
                )
            llm_model = model

        with session_scope() as session:
            session.add(
                GapReport(trigger=trigger, jobs_analyzed_count=jobs_analyzed_count, gaps=gaps, llm_model=llm_model)
            )

        return {"jobs_analyzed": jobs_analyzed_count, "gaps_found": len(gaps)}

    except Exception as exc:
        logger.exception("gap analysis failed")
        with session_scope() as session:
            session.add(
                GapReport(
                    trigger=trigger, jobs_analyzed_count=jobs_analyzed_count, gaps=[], llm_model=None, error=str(exc)
                )
            )
        return {"jobs_analyzed": jobs_analyzed_count, "gaps_found": 0, "error": str(exc)}
