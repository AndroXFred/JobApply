"""Ashby-hosted application forms (jobs.ashbyhq.com/...).

Ashby's posting page is a single-page app: the form is often revealed
in-place after clicking an "Apply" control rather than a full navigation,
so we click it if present and then wait for form fields to actually exist
before inspecting them.
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
    form_filler.click_if_present(page, "apply for this job", "apply now", "apply")

    try:
        form_filler.wait_for_any_field(page)
    except Exception:
        return ApplyOutcome(status="error", error_message="Application form never appeared on the Ashby page.")

    unmapped = form_filler.find_unmapped_required_fields(page)
    if unmapped:
        return ApplyOutcome(status="unmappable_fields", unmapped_fields=unmapped)

    form_filler.fill_known_fields(page, resume, resume_pdf_path)

    submit_button = page.query_selector(_SUBMIT_SELECTOR)
    if submit_button is None:
        return ApplyOutcome(status="error", error_message="Could not find a submit button on the Ashby form.")
    submit_button.click()

    confirmation = form_filler.wait_for_confirmation(page, _CONFIRMATION_MARKERS)
    if confirmation:
        return ApplyOutcome(status="submitted", confirmation_text=confirmation)
    return ApplyOutcome(
        status="error", error_message="Clicked submit but couldn't confirm success - check the screenshot."
    )
