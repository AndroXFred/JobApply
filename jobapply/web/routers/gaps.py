from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from jobapply.db.models import GapReport
from jobapply.db.session import session_scope
from jobapply.web import auth
from jobapply.web.scheduler import trigger_gap_analysis_now
from jobapply.web.templates_env import templates

router = APIRouter()

_HISTORY_LIMIT = 5


def _serialize(report: GapReport) -> dict:
    return {
        "id": report.id,
        "trigger": report.trigger,
        "created_at": report.created_at,
        "jobs_analyzed_count": report.jobs_analyzed_count,
        "gaps": report.gaps or [],
        "llm_model": report.llm_model,
        "error": report.error,
    }


@router.get("/gaps")
def gaps_page(request: Request, triggered: str | None = Query(None), user_id: int = Depends(auth.require_login)):
    with session_scope() as session:
        reports = session.scalars(
            select(GapReport).order_by(GapReport.created_at.desc()).limit(_HISTORY_LIMIT)
        ).all()
        serialized = [_serialize(r) for r in reports]

    return templates.TemplateResponse(
        request,
        "gaps.html",
        {
            "user_id": user_id,
            "latest": serialized[0] if serialized else None,
            "history": serialized[1:],
            "triggered": triggered == "1",
        },
    )


@router.post("/gaps/run-now")
def gaps_run_now(user_id: int = Depends(auth.require_login)):
    trigger_gap_analysis_now()
    return RedirectResponse(url="/gaps?triggered=1", status_code=303)
