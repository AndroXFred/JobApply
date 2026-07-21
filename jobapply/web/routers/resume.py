from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from jobapply.resume.importer import ResumeImportError, import_resume_yaml
from jobapply.resume.loader import resume_file_path, write_master_resume_yaml
from jobapply.web import auth
from jobapply.web.templates_env import templates

logger = logging.getLogger(__name__)

router = APIRouter()

_EXAMPLE_PATH = Path("resume/master_resume.yaml.example")
_MAX_IMPORT_SIZE = 10 * 1024 * 1024  # 10MB


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


@router.post("/resume/import")
async def resume_import(request: Request, file: UploadFile, user_id: int = Depends(auth.require_login)):
    content = await file.read()

    if len(content) > _MAX_IMPORT_SIZE:
        return templates.TemplateResponse(
            request,
            "resume_editor.html",
            {
                "user_id": user_id,
                "yaml_content": _initial_content(),
                "errors": ["That file is too large (max 10MB)."],
                "saved": False,
            },
            status_code=400,
        )

    try:
        imported_yaml = import_resume_yaml(file.filename or "upload", content)
    except ResumeImportError as exc:
        return templates.TemplateResponse(
            request,
            "resume_editor.html",
            {"user_id": user_id, "yaml_content": _initial_content(), "errors": [str(exc)], "saved": False},
            status_code=400,
        )
    except Exception:
        logger.exception("resume import failed for file %r", file.filename)
        return templates.TemplateResponse(
            request,
            "resume_editor.html",
            {
                "user_id": user_id,
                "yaml_content": _initial_content(),
                "errors": ["Something went wrong reading that file. Check the server log for details."],
                "saved": False,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "resume_editor.html",
        {
            "user_id": user_id,
            "yaml_content": imported_yaml,
            "errors": [],
            "saved": False,
            "imported_filename": file.filename,
        },
    )
