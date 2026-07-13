from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def complete_json(self, *, system: str, user: str, response_schema: type[T], model: str) -> T: ...
