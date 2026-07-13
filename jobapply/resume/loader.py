"""Phase 1 only needs to *read* the master resume as context for scoring.

The structured schema, validation, and PDF-template rendering needed for
Agent 2's tailoring land in Phase 2 — both phases read the same file, this
loader just doesn't parse/validate its structure yet.
"""

from __future__ import annotations

from pathlib import Path

from jobapply import config


def load_master_resume_text() -> str:
    path = Path(config.get_setting("resume.master_path") or "resume/master_resume.yaml")
    if not path.exists():
        raise FileNotFoundError(
            f"Master resume not found at {path}. Copy resume/master_resume.yaml.example there "
            "and fill in your real resume before running the finder/tailor agents."
        )
    return path.read_text()
