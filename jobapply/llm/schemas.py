"""Structured LLM output schemas.

Only Agent 1's output (JobEvaluation) is needed for Phase 1. Agent 2's
TailoredResume and Agent 2b's FabricationReport schemas land in Phase 2
alongside the rest of the tailoring pipeline.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RedFlag = Literal[
    # fit-relevant
    "fake_remote",
    "seniority_mismatch",
    "sponsorship_mismatch",
    # scam / ghost-job
    "unrealistic_comp",
    "urgency_language",
    "no_verifiable_company",
    "requests_financial_info",
]


class JobEvaluation(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    rationale: str
    red_flags: list[RedFlag] = Field(default_factory=list)
    recommendation: Literal["pursue", "reject"]
