"""Lever-hosted application forms (jobs.lever.co/.../apply).

The posting page (our stored job.url, Lever's `hostedUrl`) usually links to
a separate /apply page holding the actual form - try clicking an "Apply"
control first, and fall back to navigating to `{url}/apply` directly if
the URL doesn't already look like an apply page.
"""

from __future__ import annotations

from playwright.sync_api import Page

from jobapply.applier import form_filler
from jobapply.applier.platforms.base import ApplyOutcome
from jobapply.resume.schema import ResumeDocument

_SUBMIT_SELECTOR = "button[type=submit], input[type=submit]"
_CONFIRMATION_MARKERS = ("thank you", "application submitted", "successfully applied", "we've received your application")


def apply(page: Page, resume_pdf_path: str, resume: ResumeDocument) -> ApplyOutcome:
    page.wait_for_load_state("domcontentloaded")

    if not page.url.rstrip("/").endswith("/apply"):
        clicked = form_filler.click_if_present(page, "apply")
        if not clicked:
            page.goto(page.url.rstrip("/") + "/apply", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")

    unmapped = form_filler.find_unmapped_required_fields(page)
    if unmapped:
        return ApplyOutcome(status="unmappable_fields", unmapped_fields=unmapped)

    form_filler.fill_known_fields(page, resume, resume_pdf_path)

    submit_button = page.query_selector(_SUBMIT_SELECTOR)
    if submit_button is None:
        return ApplyOutcome(status="error", error_message="Could not find a submit button on the Lever form.")
    submit_button.click()

    confirmation = form_filler.wait_for_confirmation(page, _CONFIRMATION_MARKERS)
    if confirmation:
        return ApplyOutcome(status="submitted", confirmation_text=confirmation)
    return ApplyOutcome(
        status="error", error_message="Clicked submit but couldn't confirm success - check the screenshot."
    )
