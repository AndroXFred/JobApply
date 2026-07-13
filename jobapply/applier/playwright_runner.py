from __future__ import annotations

import logging
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from jobapply import config
from jobapply.applier.platforms import ashby, greenhouse, lever
from jobapply.applier.platforms.base import ApplyOutcome
from jobapply.resume.schema import ResumeDocument

logger = logging.getLogger(__name__)

_PLATFORM_MODULES = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def detect_platform(url: str) -> str | None:
    lowered = url.lower()
    if "greenhouse.io" in lowered:
        return "greenhouse"
    if "lever.co" in lowered:
        return "lever"
    if "ashbyhq.com" in lowered:
        return "ashby"
    return None


def run_application(platform: str, url: str, resume_pdf_path: str, resume: ResumeDocument, job_id: int) -> ApplyOutcome:
    module = _PLATFORM_MODULES[platform]

    screenshot_dir = Path(config.get_setting("playwright.screenshot_dir") or "data/evidence") / str(job_id)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(screenshot_dir / "confirmation.png")
    headless = config.get_bool("playwright.headless")

    # Unset by default - normal `playwright install chromium` resolution
    # applies. Only needed for environments with a non-standard browser
    # install location.
    launch_kwargs = {"headless": headless}
    executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if executable_path:
        launch_kwargs["executable_path"] = executable_path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            outcome = module.apply(page, resume_pdf_path, resume)
        except Exception as exc:
            logger.exception("playwright automation failed for job %s", job_id)
            outcome = ApplyOutcome(status="error", error_message=str(exc))
        finally:
            try:
                page.screenshot(path=screenshot_path, full_page=True)
            except Exception:
                logger.exception("failed to capture screenshot for job %s", job_id)
                screenshot_path = ""
            browser.close()

    outcome.screenshot_path = screenshot_path
    return outcome
