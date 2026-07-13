from __future__ import annotations

from jobapply.sources.ashby import AshbySource
from jobapply.sources.base import JobSource
from jobapply.sources.greenhouse import GreenhouseSource
from jobapply.sources.jsearch import JSearchSource
from jobapply.sources.lever import LeverSource

ALL_SOURCES: list[JobSource] = [
    GreenhouseSource(),
    LeverSource(),
    AshbySource(),
    JSearchSource(),
]
