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
