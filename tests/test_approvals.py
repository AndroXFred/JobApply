from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from jobapply.db.models import Approval, Job, StatusHistory
from jobapply.db.session import session_scope
from jobapply.web.routers import approvals


def _seed_pending_approval_job() -> int:
    with session_scope() as session:
        job = Job(
            source="greenhouse",
            external_id="1",
            company="Acme",
            title="Engineer",
            url="https://x",
            status="pending_approval",
            raw_json={},
        )
        session.add(job)
        session.flush()
        session.add(Approval(job_id=job.id, decision="pending", notified_at=dt.datetime.now(dt.timezone.utc)))
        return job.id


def test_approve_job_transitions_status_and_approval(temp_db):
    job_id = _seed_pending_approval_job()

    approvals.approve_job(job_id, user_id=1)

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "approved"
        approval = session.scalar(select(Approval).where(Approval.job_id == job_id))
        assert approval.decision == "approved"
        assert approval.decided_at is not None
        history = session.scalars(select(StatusHistory).where(StatusHistory.job_id == job_id)).all()
        assert history[-1].to_status == "approved"
        assert history[-1].changed_by == "human"


def test_reject_job_transitions_status_and_approval(temp_db):
    job_id = _seed_pending_approval_job()

    approvals.reject_job(job_id, user_id=1)

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "rejected_by_human"
        approval = session.scalar(select(Approval).where(Approval.job_id == job_id))
        assert approval.decision == "rejected"


def test_approve_job_rejects_when_not_pending_approval(temp_db):
    with session_scope() as session:
        job = Job(source="greenhouse", external_id="2", company="Acme", title="Eng", url="https://x", status="rejected", raw_json={})
        session.add(job)
        session.flush()
        job_id = job.id

    with pytest.raises(HTTPException) as exc_info:
        approvals.approve_job(job_id, user_id=1)
    assert exc_info.value.status_code == 409


def test_approve_job_404_for_missing_job(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        approvals.approve_job(99999, user_id=1)
    assert exc_info.value.status_code == 404
