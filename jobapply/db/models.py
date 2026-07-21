"""SQLAlchemy models for the JobApply pipeline.

Status flow for `jobs.status`:
    new -> evaluated -> (rejected | pending_tailor)
         -> (tailoring_failed | pending_approval)
         -> (approved | rejected_by_human)
         -> (applying -> applied | apply_failed)

Rejected jobs are never deleted, only status-flagged, so they stay visible
in the dashboard.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    """Seeded with exactly one row at /setup today.

    evaluations/tailored_resumes/applications/approvals/status_history/settings
    each carry an owner_id so a second real account is "add a row + a login
    form" later, not a schema migration. `jobs` stays unowned/shared since a
    posting is relevant to anyone.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # jsearch | greenhouse | lever | ashby
    external_id: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # remote|hybrid|onsite|unknown
    url: Mapped[str] = mapped_column(Text)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    normalized_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    duplicate_of_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSON)

    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    tailored_resumes: Mapped[list["TailoredResume"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    status_history: Mapped[list["StatusHistory"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    fit_score: Mapped[int] = mapped_column(Integer)  # 0-100
    rationale: Mapped[str] = mapped_column(Text)
    red_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(20))  # pursue | reject
    key_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)  # feeds the Gap Advisor
    llm_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))

    job: Mapped[Job] = relationship(back_populates="evaluations")


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    structured_json: Mapped[dict] = mapped_column(JSON)
    pdf_path: Mapped[str] = mapped_column(Text)
    fabrication_check_passed: Mapped[bool] = mapped_column(Boolean)
    fabrication_check_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str] = mapped_column(String(100))

    job: Mapped[Job] = relationship(back_populates="tailored_resumes")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tailored_resume_id: Mapped[int | None] = mapped_column(ForeignKey("tailored_resumes.id"), nullable=True)
    ats_platform: Mapped[str] = mapped_column(String(30))  # greenhouse | lever | ashby
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|submitted|failed
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    job: Mapped[Job] = relationship(back_populates="applications")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    notified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="approvals")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    changed_by: Mapped[str] = mapped_column(String(20))  # agent1|agent2|agent3|human|system
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="status_history")


class Setting(Base):
    """Backs both the /setup wizard and the Settings page.

    Secret values (is_secret=True) are write-only in the UI: the form shows
    a masked placeholder and only overwrites the stored value if the user
    types a new one.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class PipelineRun(Base):
    """One row per scheduled/manual pipeline run, so a failure (missing
    resume, bad API key, network error, ...) is visible on the dashboard
    instead of only in the server log."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20))  # cron | manual
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finder_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finder_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tailor_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tailor_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applier_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    applier_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class GapReport(Base):
    """Output of the Gap Advisor: recurring skill/qualification gaps
    between the master resume and recent job postings, with recommended
    certifications/courses. Strictly advisory - nothing here ever writes
    back to the resume."""

    __tablename__ = "gap_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20))  # cron | manual
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    jobs_analyzed_count: Mapped[int] = mapped_column(Integer)
    gaps: Mapped[list[dict]] = mapped_column(JSON, default=list)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # visible on /gaps instead of only the log
