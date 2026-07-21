"""Agent 2 (tailor) + Agent 2b (fabrication auditor).

Two-pass anti-fabrication guardrail: a cheap deterministic numeric
pre-check runs first and can short-circuit before spending an LLM call: any
number in the tailored resume that doesn't appear anywhere in the master
resume is treated as fabrication (accepting some false-positive risk on
reformatted numbers, since failing safe here just costs a retry, not a
false approval). If that passes, a separate LLM call audits every
substantive claim against the master resume. Only jobs that clear both
checks get a rendered PDF and move to pending_approval.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from sqlalchemy import select

from jobapply.db.models import Approval, Evaluation, Job, TailoredResume
from jobapply.db.session import session_scope
from jobapply.db.status import record_status
from jobapply.llm.client import OpenAICompatClient, get_client_for
from jobapply.llm.schemas import FabricationCheckResult
from jobapply.notify import ntfy
from jobapply.resume.loader import load_master_resume
from jobapply.resume.render import render_resume_pdf
from jobapply.resume.schema import ResumeDocument, resume_text_blob

_PROMPT_DIR = Path(__file__).parent / "prompts"
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _read_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text()


def _numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


def _numeric_precheck(master: ResumeDocument, tailored: ResumeDocument) -> str | None:
    unmatched = sorted(_numbers_in(resume_text_blob(tailored)) - _numbers_in(resume_text_blob(master)))
    if not unmatched:
        return None
    return f"Numbers in the tailored resume with no match anywhere in the master resume: {', '.join(unmatched)}"


def _tailor_resume(client: OpenAICompatClient, model: str, master: ResumeDocument, job: Job) -> ResumeDocument:
    user_prompt = (
        f"## Master resume\n{master.model_dump_json(indent=2)}\n\n"
        f"## Job posting\nCompany: {job.company}\nTitle: {job.title}\n\n"
        f"Description:\n{job.description_raw or '(no description provided)'}"
    )
    return client.complete_json(
        system=_read_prompt("tailor_system.md"), user=user_prompt, response_schema=ResumeDocument, model=model
    )


def _audit_resume(
    client: OpenAICompatClient, model: str, master: ResumeDocument, tailored: ResumeDocument
) -> FabricationCheckResult:
    user_prompt = (
        f"## Master resume\n{master.model_dump_json(indent=2)}\n\n"
        f"## Tailored resume\n{tailored.model_dump_json(indent=2)}"
    )
    return client.complete_json(
        system=_read_prompt("fabrication_check_system.md"),
        user=user_prompt,
        response_schema=FabricationCheckResult,
        model=model,
    )


def _latest_fit_score(session, job_id: int) -> int | None:
    evaluation = session.scalar(
        select(Evaluation).where(Evaluation.job_id == job_id).order_by(Evaluation.created_at.desc())
    )
    return evaluation.fit_score if evaluation else None


def run_tailor(job_id: int | None = None) -> dict[str, int]:
    master = load_master_resume()
    tailor_client, tailor_model = get_client_for("tailor")
    audit_client, audit_model = get_client_for("fabrication_check")

    with session_scope() as session:
        query = select(Job.id).where(Job.status == "pending_tailor")
        if job_id is not None:
            query = query.where(Job.id == job_id)
        job_ids = list(session.scalars(query).all())

    stats = {"processed": 0, "tailored": 0, "blocked": 0, "failed": 0}

    for jid in job_ids:
        stats["processed"] += 1
        with session_scope() as session:
            job = session.get(Job, jid)

            try:
                tailored = _tailor_resume(tailor_client, tailor_model, master, job)
            except Exception:
                record_status(session, job, "tailoring_failed", changed_by="agent2", note="tailor LLM call failed")
                stats["failed"] += 1
                continue

            precheck_issue = _numeric_precheck(master, tailored)
            if precheck_issue:
                session.add(
                    TailoredResume(
                        job_id=job.id,
                        structured_json=tailored.model_dump(mode="json"),
                        pdf_path="",
                        fabrication_check_passed=False,
                        fabrication_check_notes=precheck_issue,
                        llm_model=tailor_model,
                    )
                )
                record_status(session, job, "tailoring_failed", changed_by="agent2", note=precheck_issue)
                stats["blocked"] += 1
                continue

            try:
                audit = _audit_resume(audit_client, audit_model, master, tailored)
            except Exception:
                record_status(
                    session, job, "tailoring_failed", changed_by="agent2", note="fabrication audit LLM call failed"
                )
                stats["failed"] += 1
                continue

            passed = bool(audit.claims) and all(c.verdict == "supported" for c in audit.claims)
            notes = "\n".join(
                f"[{c.verdict}] {c.claim}" + (f" — {c.master_source_ref}" if c.master_source_ref else "")
                for c in audit.claims
            )

            pdf_path = render_resume_pdf(tailored, job.id) if passed else ""

            session.add(
                TailoredResume(
                    job_id=job.id,
                    structured_json=tailored.model_dump(mode="json"),
                    pdf_path=pdf_path,
                    fabrication_check_passed=passed,
                    fabrication_check_notes=notes,
                    llm_model=tailor_model,
                )
            )

            if passed:
                record_status(session, job, "pending_approval", changed_by="agent2")
                session.add(Approval(job_id=job.id, decision="pending", notified_at=dt.datetime.now(dt.timezone.utc)))
                stats["tailored"] += 1
                fit_score = _latest_fit_score(session, job.id)
                ntfy.publish(job, fit_score=fit_score)
            else:
                record_status(
                    session, job, "tailoring_failed", changed_by="agent2", note="fabrication check found unsupported claims"
                )
                stats["blocked"] += 1

    return stats
