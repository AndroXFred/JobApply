"""Structured LLM output schemas."""

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


class ClaimVerdict(BaseModel):
    claim: str
    verdict: Literal["supported", "unsupported"]
    master_source_ref: str | None = None


class FabricationCheckResult(BaseModel):
    """Agent 2b's output. `passed` is deliberately not part of this schema -
    it's derived in code from the claims list so the LLM can't self-report
    an inconsistent verdict (e.g. passed=true alongside an unsupported claim).
    """

    claims: list[ClaimVerdict] = Field(default_factory=list)
