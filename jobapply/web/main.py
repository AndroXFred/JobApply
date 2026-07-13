from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from jobapply import config
from jobapply.db.migrate import run_migrations
from jobapply.web.scheduler import reschedule_finder, scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.is_setup_complete():
        reschedule_finder()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    # Run before anything reads settings (e.g. the cookie-security check
    # below) - migrations are otherwise only guaranteed by the async
    # lifespan, which runs too late for that synchronous read.
    run_migrations()

    app = FastAPI(title="JobApply", lifespan=lifespan)

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from jobapply.web.routers import approvals, auth as auth_router
    from jobapply.web.routers import jobs, pipeline, settings, setup

    app.include_router(auth_router.router)
    app.include_router(setup.router)
    app.include_router(settings.router)
    app.include_router(jobs.router)
    app.include_router(pipeline.router)
    app.include_router(approvals.router)

    @app.middleware("http")
    async def _gate(request: Request, call_next):
        path = request.url.path
        if path.startswith(("/static", "/setup")):
            return await call_next(request)
        if not config.is_setup_complete():
            return RedirectResponse(url="/setup")
        if path == "/login":
            return await call_next(request)
        if not request.session.get("user_id"):
            return RedirectResponse(url="/login")
        if path == "/":
            return RedirectResponse(url="/jobs")
        return await call_next(request)

    # Added last so it's outermost in the middleware stack (Starlette wraps
    # last-added = outermost = runs first) - _gate above depends on
    # request.session already being populated by SessionMiddleware.
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # Dev fallback: sessions won't survive a restart. Set SECRET_KEY in
        # .env for a stable session across app restarts.
        secret = secrets.token_hex(32)
        logger.warning("SECRET_KEY not set; using an ephemeral session secret for this run only.")
    # Secure cookie only over https - dashboard.base_url flips to your public
    # Cloudflare Tunnel hostname once that's set up (see Settings). This is
    # read once at process start, so changing dashboard.base_url later needs
    # an app restart to take effect on the cookie flag.
    https_only = (config.get_setting("dashboard.base_url") or "").startswith("https://")
    app.add_middleware(SessionMiddleware, secret_key=secret, https_only=https_only)

    return app


app = create_app()
