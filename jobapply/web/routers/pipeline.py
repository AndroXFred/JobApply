from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from jobapply.web import auth
from jobapply.web.scheduler import trigger_pipeline_now

router = APIRouter()


@router.post("/pipeline/run-now")
def run_now(user_id: int = Depends(auth.require_login)):
    trigger_pipeline_now()
    return RedirectResponse(url="/jobs?triggered=1", status_code=303)
