from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from jobapply import config
from jobapply.web import auth
from jobapply.web.templates_env import templates

router = APIRouter()


@router.get("/setup")
def setup_form(request: Request):
    if config.is_setup_complete():
        return RedirectResponse(url="/jobs")
    return templates.TemplateResponse(request, "setup.html", {"user_id": None, "values": {}, "errors": []})


@router.post("/setup")
def setup_submit(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    llm_profile: str = Form("gemini"),
    gemini_api_key: str = Form(""),
    local_base_url: str = Form("http://localhost:8080/v1"),
    rapidapi_key: str = Form(""),
    jsearch_query: str = Form("software engineer remote"),
    jsearch_location: str = Form(""),
    greenhouse_boards: str = Form(""),
    lever_boards: str = Form(""),
    ashby_boards: str = Form(""),
    fit_score_threshold: str = Form("70"),
    ntfy_base_url: str = Form("https://ntfy.sh"),
    ntfy_topic: str = Form(""),
    ntfy_auth_token: str = Form(""),
    dashboard_base_url: str = Form("http://localhost:8000"),
    finder_cron: str = Form("0 8-22/3 * * *"),
    timezone: str = Form("UTC"),
):
    if config.is_setup_complete():
        return RedirectResponse(url="/jobs")

    errors: list[str] = []
    if llm_profile == "gemini" and not gemini_api_key:
        errors.append("A Gemini API key is required when the LLM profile is 'gemini'.")
    if not ntfy_topic:
        errors.append("An ntfy topic is required for the approval-gate notification.")
    has_jsearch = bool(rapidapi_key)
    has_boards = bool(greenhouse_boards or lever_boards or ashby_boards)
    if not has_jsearch and not has_boards:
        errors.append("Configure at least one job source: a RapidAPI key, or a Greenhouse/Lever/Ashby board.")

    if errors:
        values = {
            "email": email,
            "display_name": display_name,
            "llm_profile": llm_profile,
            "local_base_url": local_base_url,
            "jsearch_query": jsearch_query,
            "jsearch_location": jsearch_location,
            "greenhouse_boards": greenhouse_boards,
            "lever_boards": lever_boards,
            "ashby_boards": ashby_boards,
            "fit_score_threshold": fit_score_threshold,
            "ntfy_base_url": ntfy_base_url,
            "dashboard_base_url": dashboard_base_url,
            "finder_cron": finder_cron,
            "timezone": timezone,
        }
        return templates.TemplateResponse(
            request, "setup.html", {"user_id": None, "values": values, "errors": errors}, status_code=400
        )

    user_id = auth.create_user(email=email, display_name=display_name, password=password)

    config.set_setting("llm.profile", llm_profile)
    config.set_setting("llm.gemini.api_key", gemini_api_key or None)
    config.set_setting("llm.local.base_url", local_base_url)
    config.set_setting("sources.jsearch.api_key", rapidapi_key or None)
    config.set_setting("sources.jsearch.enabled", "true" if rapidapi_key else "false")
    config.set_setting("sources.jsearch.query", jsearch_query)
    config.set_setting("sources.jsearch.location", jsearch_location)
    config.set_setting("sources.greenhouse.boards", greenhouse_boards)
    config.set_setting("sources.greenhouse.enabled", "true" if greenhouse_boards else "false")
    config.set_setting("sources.lever.boards", lever_boards)
    config.set_setting("sources.lever.enabled", "true" if lever_boards else "false")
    config.set_setting("sources.ashby.boards", ashby_boards)
    config.set_setting("sources.ashby.enabled", "true" if ashby_boards else "false")
    config.set_setting("scoring.fit_score_threshold", fit_score_threshold)
    config.set_setting("notify.ntfy.base_url", ntfy_base_url)
    config.set_setting("notify.ntfy.topic", ntfy_topic)
    config.set_setting("notify.ntfy.auth_token", ntfy_auth_token or None)
    config.set_setting("dashboard.base_url", dashboard_base_url)
    config.set_setting("scheduler.finder_cron", finder_cron)
    config.set_setting("scheduler.timezone", timezone)

    from jobapply.web.scheduler import reschedule_finder

    reschedule_finder()

    request.session[auth.SESSION_USER_KEY] = user_id
    return RedirectResponse(url="/jobs", status_code=303)
