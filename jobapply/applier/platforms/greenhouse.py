"""Greenhouse-hosted application forms (boards.greenhouse.io/.../jobs/...).

Native Greenhouse job pages render the form directly on the page; the
iframe path below only applies to some third-party embeds, kept as a
defensive fallback since we can't verify every company's setup live.
"""

from __future__ import annotations

from playwright.sync_api import Page

from jobapply.applier import form_filler
from jobapply.applier.platforms.base import ApplyOutcome
from jobapply.resume.schema import ResumeDocument

_SUBMIT_SELECTOR = "#submit_app, button[type=submit], input[type=submit]"
_CONFIRMATION_MARKERS = ("thank you", "successfully applied", "application received", "we've received your application")


def apply(page: Page, resume_pdf_path: str, resume: ResumeDocument) -> ApplyOutcome:
    page.wait_for_load_state("domcontentloaded")

    scope = page
    iframe_el = page.query_selector("iframe#grnhse_iframe, iframe[src*='greenhouse']")
    if iframe_el:
        frame = iframe_el.content_frame()
        if frame:
            scope = frame

    unmapped = form_filler.find_unmapped_required_fields(scope)
    if unmapped:
        return ApplyOutcome(status="unmappable_fields", unmapped_fields=unmapped)

    form_filler.fill_known_fields(scope, resume, resume_pdf_path)

    submit_button = scope.query_selector(_SUBMIT_SELECTOR)
    if submit_button is None:
        return ApplyOutcome(status="error", error_message="Could not find a submit button on the Greenhouse form.")
    submit_button.click()

    confirmation = form_filler.wait_for_confirmation(page, _CONFIRMATION_MARKERS)
    if confirmation:
        return ApplyOutcome(status="submitted", confirmation_text=confirmation)
    return ApplyOutcome(
        status="error", error_message="Clicked submit but couldn't confirm success - check the screenshot."
    )
