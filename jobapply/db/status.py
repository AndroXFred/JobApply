from __future__ import annotations

from jobapply.db.models import Job, StatusHistory


def record_status(session, job: Job, to_status: str, changed_by: str, note: str | None = None) -> None:
    session.add(
        StatusHistory(job_id=job.id, from_status=job.status, to_status=to_status, changed_by=changed_by, note=note)
    )
    job.status = to_status
