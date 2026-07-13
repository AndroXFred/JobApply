from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from jobapply.web import auth
from jobapply.web.templates_env import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user_id": auth.current_user_id(request)})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user_id = auth.authenticate(email, password)
    if user_id is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password.", "user_id": None}, status_code=401
        )
    request.session[auth.SESSION_USER_KEY] = user_id
    return RedirectResponse(url="/jobs", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
