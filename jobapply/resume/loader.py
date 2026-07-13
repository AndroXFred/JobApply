"""Phase 1 (Agent 1) reads the master resume as free-form text context for
scoring. Phase 2 (Agent 2 / 2b / PDF rendering) needs it validated and
structured, via load_master_resume() below - both read the same file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from jobapply import config
from jobapply.resume.schema import ResumeDocument


def _resume_path() -> Path:
    path = Path(config.get_setting("resume.master_path") or "resume/master_resume.yaml")
    if not path.exists():
        raise FileNotFoundError(
            f"Master resume not found at {path}. Copy resume/master_resume.yaml.example there "
            "and fill in your real resume before running the finder/tailor agents."
        )
    return path


def load_master_resume_text() -> str:
    return _resume_path().read_text()


def load_master_resume() -> ResumeDocument:
    data = yaml.safe_load(_resume_path().read_text())
    return ResumeDocument.model_validate(data)
