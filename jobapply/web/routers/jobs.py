from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select

from jobapply.db.models import Application, Job, PipelineRun
from jobapply.db.session import session_scope
from jobapply.resume.loader import resume_exists
from jobapply.web import auth
from jobapply.web.templates_env import templates

router = APIRouter()

STATUS_OPTIONS = [
    "new",
    "evaluated",
    "rejected",
    "pending_tailor",
    "tailoring_failed",
    "pending_approval",
    "approved",
    "rejected_by_human",
    "applying",
    "applied",
    "apply_failed",
    "evaluation_failed",
]


def _latest_evaluation(job: Job):
    return max(job.evaluations, key=lambda e: e.created_at, default=None)


@router.get("/jobs")
def job_list(
    request: Request,
    status: str | None = Query(None),
    min_score: int | None = Query(None),
    triggered: str | None = Query(None),
    user_id: int = Depends(auth.require_login),
):
    with session_scope() as session:
        last_run_row = session.scalar(select(PipelineRun).order_by(PipelineRun.started_at.desc()))
        last_run = (
            {
                "trigger": last_run_row.trigger,
                "started_at": last_run_row.started_at,
                "finished_at": last_run_row.finished_at,
                "stages": [
                    {"name": "finder", "stats": last_run_row.finder_stats, "error": last_run_row.finder_error},
                    {"name": "tailor", "stats": last_run_row.tailor_stats, "error": last_run_row.tailor_error},
                    {"name": "applier", "stats": last_run_row.applier_stats, "error": last_run_row.applier_error},
                ],
            }
            if last_run_row
            else None
        )

        jobs = session.scalars(select(Job).order_by(Job.first_seen_at.desc())).all()
        counts: dict[str, int] = {}
        rows = []
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
            latest_eval = _latest_evaluation(job)
            if status and job.status != status:
                continue
            if min_score is not None and (not latest_eval or latest_eval.fit_score < min_score):
                continue
            rows.append(
                {
                    "id": job.id,
                    "company": job.company,
                    "title": job.title,
                    "location": job.location,
                    "remote_type": job.remote_type,
                    "status": job.status,
                    "source": job.source,
                    "url": job.url,
                    "first_seen_at": job.first_seen_at,
                    "duplicate": job.duplicate_of_job_id is not None,
                    "fit_score": latest_eval.fit_score if latest_eval else None,
                    "red_flags": latest_eval.red_flags if latest_eval else [],
                }
            )

    return templates.TemplateResponse(
        request,
        "job_list.html",
        {
            "user_id": user_id,
            "jobs": rows,
            "counts": counts,
            "status_options": STATUS_OPTIONS,
            "status_filter": status,
            "min_score": min_score,
            "triggered": triggered == "1",
            "resume_missing": not resume_exists(),
            "last_run": last_run,
        },
    )


@router.get("/jobs/{job_id}")
def job_detail(request: Request, job_id: int, user_id: int = Depends(auth.require_login)):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluations = sorted(job.evaluations, key=lambda e: e.created_at, reverse=True)
        tailored_resumes = sorted(job.tailored_resumes, key=lambda t: t.created_at, reverse=True)
        applications = sorted(job.applications, key=lambda a: a.id, reverse=True)
        history = sorted(job.status_history, key=lambda h: h.changed_at, reverse=True)

        data = {
            "job": {
                "id": job.id,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "remote_type": job.remote_type,
                "status": job.status,
                "source": job.source,
                "url": job.url,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "posted_at": job.posted_at,
                "first_seen_at": job.first_seen_at,
                "last_seen_at": job.last_seen_at,
                "description_raw": job.description_raw,
                "duplicate_of_job_id": job.duplicate_of_job_id,
            },
            "evaluations": [
                {
                    "created_at": e.created_at,
                    "fit_score": e.fit_score,
                    "rationale": e.rationale,
                    "red_flags": e.red_flags,
                    "recommendation": e.recommendation,
                    "llm_model": e.llm_model,
                }
                for e in evaluations
            ],
            "tailored_resumes": [
                {
                    "id": t.id,
                    "created_at": t.created_at,
                    "has_pdf": bool(t.pdf_path),
                    "fabrication_check_passed": t.fabrication_check_passed,
                    "fabrication_check_notes": t.fabrication_check_notes,
                    "llm_model": t.llm_model,
                }
                for t in tailored_resumes
            ],
            "applications": [
                {
                    "id": a.id,
                    "ats_platform": a.ats_platform,
                    "status": a.status,
                    "submitted_at": a.submitted_at,
                    "has_screenshot": bool(a.confirmation_screenshot_path),
                    "confirmation_text": a.confirmation_text,
                    "error_message": a.error_message,
                }
                for a in applications
            ],
            "history": [
                {
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "changed_at": h.changed_at,
                    "changed_by": h.changed_by,
                    "note": h.note,
                }
                for h in history
            ],
        }

    return templates.TemplateResponse(request, "job_detail.html", {"user_id": user_id, **data})


@router.get("/jobs/{job_id}/resume.pdf")
def job_resume_pdf(job_id: int, user_id: int = Depends(auth.require_login)):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        latest = max(job.tailored_resumes, key=lambda t: t.created_at, default=None)
        if latest is None or not latest.pdf_path:
            raise HTTPException(status_code=404, detail="No tailored resume PDF available for this job")
        pdf_path = latest.pdf_path

    return FileResponse(pdf_path, media_type="application/pdf", filename=f"resume_job_{job_id}.pdf")


@router.get("/applications/{application_id}/screenshot.png")
def application_screenshot(application_id: int, user_id: int = Depends(auth.require_login)):
    with session_scope() as session:
        application = session.get(Application, application_id)
        if application is None or not application.confirmation_screenshot_path:
            raise HTTPException(status_code=404, detail="No screenshot available for this application")
        screenshot_path = application.confirmation_screenshot_path

    return FileResponse(screenshot_path, media_type="image/png")
