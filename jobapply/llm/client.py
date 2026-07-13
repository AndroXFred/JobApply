"""The one LLM client implementation.

Both Gemini (via its OpenAI-compatible endpoint,
https://ai.google.dev/gemini-api/docs/openai) and a local llama-server
speak the same wire protocol, so provider selection is pure config
(jobapply.config.llm_profile_config) — there is deliberately no per-provider
subclass.

response_schema.model_json_schema() emits standard JSON Schema with
$defs/$ref for nested models (e.g. ResumeDocument's experience/education
lists) — both OpenAI's and Gemini's json_schema structured-output modes are
expected to support this, but it's worth checking against a real response
the first time a new nested schema is added, since support for $ref depth
varies across providers.
"""

from __future__ import annotations

from typing import TypeVar

import openai
from pydantic import BaseModel

from jobapply import config

T = TypeVar("T", bound=BaseModel)

AgentName = str  # "finder" | "tailor" | "fabrication_check"


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key or "not-needed")

    def complete_json(self, *, system: str, user: str, response_schema: type[T], model: str) -> T:
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty content")
        return response_schema.model_validate_json(content)


def get_client_for(agent: AgentName) -> tuple[OpenAICompatClient, str]:
    """(client, model_name) for the given agent, using the active LLM profile."""
    cfg = config.llm_profile_config()
    client = OpenAICompatClient(base_url=cfg["base_url"], api_key=cfg["api_key"])
    model = cfg[f"model_{agent}"]
    if not model:
        raise ValueError(f"No model configured for agent {agent!r} on profile {cfg['profile']!r}")
    return client, model
