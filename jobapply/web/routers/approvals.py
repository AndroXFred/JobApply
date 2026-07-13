from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from jobapply.db.models import Approval, Job
from jobapply.db.session import session_scope
from jobapply.db.status import record_status
from jobapply.web import auth

router = APIRouter()


def _decide(job_id: int, decision: str, to_status: str) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "pending_approval":
            raise HTTPException(status_code=409, detail=f"Job is not pending approval (status: {job.status})")

        approval = session.scalar(
            select(Approval).where(Approval.job_id == job_id).order_by(Approval.notified_at.desc())
        )
        if approval:
            approval.decision = decision
            approval.decided_at = dt.datetime.now(dt.timezone.utc)

        record_status(session, job, to_status, changed_by="human")


@router.post("/jobs/{job_id}/approve")
def approve_job(job_id: int, user_id: int = Depends(auth.require_login)):
    _decide(job_id, decision="approved", to_status="approved")
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/reject")
def reject_job(job_id: int, user_id: int = Depends(auth.require_login)):
    _decide(job_id, decision="rejected", to_status="rejected_by_human")
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
