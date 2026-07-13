from __future__ import annotations

import datetime as dt
from typing import Any, Protocol

from pydantic import BaseModel


class RawJob(BaseModel):
    source: str
    external_id: str
    company: str
    title: str
    location: str | None = None
    remote_type: str | None = None  # remote | hybrid | onsite | unknown
    url: str
    description_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: dt.datetime | None = None
    raw: dict[str, Any] = {}


class JobSource(Protocol):
    name: str

    def fetch(self) -> list[RawJob]: ...


def humanize_token(token: str) -> str:
    """Best-effort company display name from a board/site slug (e.g. 'acme-corp' -> 'Acme Corp')."""
    return " ".join(part.capitalize() for part in token.replace("_", "-").split("-") if part)

