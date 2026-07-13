from __future__ import annotations

import os
from pathlib import Path

import pytest

# Some sandboxed CI environments pre-install Chromium at a nonstandard path
# that Playwright's default resolution doesn't find. Only opt into it when
# that exact path exists - on a normal `playwright install chromium` setup
# (i.e. a real deployment) this stays a no-op and default resolution applies.
_SANDBOX_CHROMIUM = "/opt/pw-browsers/chromium"
if "PLAYWRIGHT_CHROMIUM_PATH" not in os.environ and Path(_SANDBOX_CHROMIUM).exists():
    os.environ["PLAYWRIGHT_CHROMIUM_PATH"] = _SANDBOX_CHROMIUM


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    launch_kwargs = {"headless": True}
    executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if executable_path:
        launch_kwargs["executable_path"] = executable_path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    import jobapply.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None

    from jobapply.db.migrate import run_migrations

    run_migrations()
    yield db_path

    session_module._engine = None
    session_module._SessionLocal = None
