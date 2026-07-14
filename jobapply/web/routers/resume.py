from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from jobapply.resume.loader import resume_file_path, write_master_resume_yaml
from jobapply.web import auth
from jobapply.web.templates_env import templates

router = APIRouter()

_EXAMPLE_PATH = Path("resume/master_resume.yaml.example")


def _initial_content() -> str:
    path = resume_file_path()
    if path.exists():
        return path.read_text()
    if _EXAMPLE_PATH.exists():
        return _EXAMPLE_PATH.read_text()
    return ""


@router.get("/resume")
def resume_form(request: Request, saved: str | None = Query(None), user_id: int = Depends(auth.require_login)):
    return templates.TemplateResponse(
        request,
        "resume_editor.html",
        {"user_id": user_id, "yaml_content": _initial_content(), "errors": [], "saved": saved == "1"},
    )


def validate_and_save(yaml_content: str) -> list[str]:
    """Returns a list of human-readable error strings (empty on success).
    Pulled out of the route so it's testable without a Request/template
    stack - the route below is just plumbing around this."""
    errors: list[str] = []
    try:
        write_master_resume_yaml(yaml_content)
    except yaml.YAMLError as exc:
        errors.append(f"Invalid YAML: {exc}")
    except ValidationError as exc:
        for e in exc.errors():
            loc = ".".join(str(p) for p in e["loc"])
            errors.append(f"{loc}: {e['msg']}")
    return errors


@router.post("/resume")
def resume_submit(request: Request, yaml_content: str = Form(...), user_id: int = Depends(auth.require_login)):
    errors = validate_and_save(yaml_content)

    if errors:
        return templates.TemplateResponse(
            request,
            "resume_editor.html",
            {"user_id": user_id, "yaml_content": yaml_content, "errors": errors, "saved": False},
            status_code=400,
        )

    return RedirectResponse(url="/resume?saved=1", status_code=303)
