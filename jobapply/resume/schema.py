"""Structured resume shape, shared by the master resume file, Agent 2's
tailored output, and the PDF render template."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class ExperienceEntry(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: str  # "present" allowed
    location: str | None = None
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str
    degree: str
    end_date: str | None = None


class ResumeConstraints(BaseModel):
    requires_visa_sponsorship: bool = False
    minimum_salary_usd: int | None = None


class ResumeDocument(BaseModel):
    contact: ContactInfo
    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    constraints: ResumeConstraints = Field(default_factory=ResumeConstraints)


def resume_text_blob(resume: ResumeDocument) -> str:
    """Flattens the resume to searchable free text - used by Agent 2's
    numeric fabrication pre-check and the Gap Advisor's skill matching."""
    parts = [resume.summary, *resume.skills]
    for exp in resume.experience:
        parts.append(f"{exp.title} {exp.company} {exp.start_date} {exp.end_date} {exp.location or ''}")
        parts.extend(exp.bullets)
    for edu in resume.education:
        parts.append(f"{edu.degree} {edu.institution} {edu.end_date or ''}")
    return "\n".join(parts)
