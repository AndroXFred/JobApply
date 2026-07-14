"""Phase 1 (Agent 1) reads the master resume as free-form text context for
scoring. Phase 2 (Agent 2 / 2b / PDF rendering) needs it validated and
structured, via load_master_resume() below - both read the same file. The
Resume page in the dashboard (web/routers/resume.py) reads/writes the same
file too, so there's exactly one source of truth regardless of how it's
edited.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from jobapply import config
from jobapply.resume.schema import ResumeDocument


def resume_file_path() -> Path:
    return Path(config.get_setting("resume.master_path") or "resume/master_resume.yaml")


def resume_exists() -> bool:
    return resume_file_path().exists()


def _require_resume_path() -> Path:
    path = resume_file_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Master resume not found at {path}. Add one on the Resume page in the dashboard "
            "before running the finder/tailor agents."
        )
    return path


def load_master_resume_text() -> str:
    return _require_resume_path().read_text()


def load_master_resume() -> ResumeDocument:
    data = yaml.safe_load(_require_resume_path().read_text())
    return ResumeDocument.model_validate(data)


def write_master_resume_yaml(yaml_text: str) -> None:
    """Validates before writing - never leaves the file in a state the
    other agents can't parse."""
    ResumeDocument.model_validate(yaml.safe_load(yaml_text))
    path = resume_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text)
