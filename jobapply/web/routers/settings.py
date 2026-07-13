from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from jobapply import config
from jobapply.web import auth
from jobapply.web.scheduler import reschedule_finder
from jobapply.web.templates_env import templates

router = APIRouter()

_NON_SECRET_FIELDS = [
    "llm.profile",
    "llm.gemini.base_url",
    "llm.gemini.model_finder",
    "llm.gemini.model_tailor",
    "llm.gemini.model_fabrication_check",
    "llm.local.base_url",
    "llm.local.model_finder",
    "llm.local.model_tailor",
    "llm.local.model_fabrication_check",
    "sources.jsearch.host",
    "sources.jsearch.query",
    "sources.jsearch.location",
    "sources.jsearch.date_posted",
    "sources.greenhouse.boards",
    "sources.lever.boards",
    "sources.ashby.boards",
    "scoring.fit_score_threshold",
    "notify.ntfy.base_url",
    "dashboard.base_url",
    "scheduler.finder_cron",
    "scheduler.timezone",
    "resume.master_path",
    "playwright.screenshot_dir",
]

# HTML checkboxes only submit when checked, so these are handled separately:
# presence in the form means "true", absence means "false".
_BOOLEAN_FIELDS = [
    "sources.jsearch.enabled",
    "sources.jsearch.remote_jobs_only",
    "sources.greenhouse.enabled",
    "sources.lever.enabled",
    "sources.ashby.enabled",
    "playwright.headless",
]

_SECRET_FIELDS = [
    "llm.gemini.api_key",
    "llm.local.api_key",
    "sources.jsearch.api_key",
    "notify.ntfy.topic",
    "notify.ntfy.auth_token",
]


@router.get("/settings")
def settings_form(request: Request, user_id: int = Depends(auth.require_login)):
    values = config.get_all_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"user_id": user_id, "values": values, "saved": request.query_params.get("saved") == "1"},
    )


@router.post("/settings")
async def settings_submit(request: Request, user_id: int = Depends(auth.require_login)):
    form = await request.form()
    for key in _NON_SECRET_FIELDS:
        if key in form:
            config.set_setting(key, str(form[key]))
    for key in _BOOLEAN_FIELDS:
        config.set_setting(key, "true" if key in form else "false")
    for key in _SECRET_FIELDS:
        value = str(form.get(key, "")).strip()
        if value:
            config.set_setting(key, value)
    reschedule_finder()
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.post("/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    user_id: int = Depends(auth.require_login),
):
    if not auth.verify_current_password(user_id, current_password):
        values = config.get_all_settings()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"user_id": user_id, "values": values, "password_error": "Current password is incorrect."},
            status_code=400,
        )
    auth.update_password(user_id, new_password)
    return RedirectResponse(url="/settings?saved=1", status_code=303)
