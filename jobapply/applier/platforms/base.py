"""Shared types for per-platform apply modules.

The field-filling strategy (see form_filler.py) is deliberately generic
across all three ATS platforms - exact DOM structure varies per company's
customization and can't be verified against a live page from this
environment, so field detection is driven by accessible labels rather than
hardcoded selectors. Each platform module only needs to handle getting to
the form and detecting the submit/confirmation, both below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Label substrings (case-insensitive) safe to auto-fill from the master
# resume. Any *required* field found on a form that doesn't match one of
# these causes Agent 3 to bail rather than guess an answer - see the plan's
# anti-hallucination guardrail for Agent 3.
KNOWN_FIELD_LABELS = [
    "first name",
    "last name",
    "full name",
    "email",
    "phone",
    "resume",
    "cv",
    "cover letter",
    "linkedin",
    "website",
    "portfolio",
    "github",
    "location",
    "current company",
]


def is_known_label(label: str) -> bool:
    normalized = label.strip().lower()
    return bool(normalized) and any(known in normalized for known in KNOWN_FIELD_LABELS)


@dataclass
class ApplyOutcome:
    status: Literal["submitted", "unmappable_fields", "error"]
    confirmation_text: str | None = None
    unmapped_fields: list[str] = field(default_factory=list)
    error_message: str | None = None
    screenshot_path: str = ""
