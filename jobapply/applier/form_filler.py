"""Generic, label-driven form filling shared by all three platform modules.

Exact DOM structure (field names/IDs) varies per company's customization of
their ATS and can't be verified against a live page from this environment,
so fields are matched by their human-readable label rather than hardcoded
selectors - the same approach a person skimming the form would use.
"""

from __future__ import annotations

import logging
from typing import Union

from playwright.sync_api import ElementHandle, Frame, Page

from jobapply.applier.platforms.base import is_known_label
from jobapply.resume.schema import ResumeDocument

logger = logging.getLogger(__name__)

PageOrFrame = Union[Page, Frame]

_FIELD_SELECTOR = (
    "input:not([type=hidden]):not([type=submit]):not([type=button])"
    ":not([type=checkbox]):not([type=radio]), textarea, select"
)


def _label_for(scope: PageOrFrame, element: ElementHandle) -> str:
    aria = element.get_attribute("aria-label")
    if aria and aria.strip():
        return aria.strip()
    el_id = element.get_attribute("id")
    if el_id:
        label_el = scope.query_selector(f'label[for="{el_id}"]')
        if label_el:
            text = label_el.inner_text().strip()
            if text:
                return text
    placeholder = element.get_attribute("placeholder")
    if placeholder and placeholder.strip():
        return placeholder.strip()
    return (element.get_attribute("name") or "").strip()


def wait_for_any_field(page: Page, timeout: int = 10000) -> None:
    """Raises TimeoutError if no form field ever appears - used by SPA-style
    platforms (Ashby) where the form is revealed dynamically rather than
    present on initial page load."""
    page.wait_for_selector(_FIELD_SELECTOR, timeout=timeout)


def _enumerate_fields(scope: PageOrFrame, *, required_only: bool) -> list[tuple[str, ElementHandle]]:
    fields: list[tuple[str, ElementHandle]] = []
    for el in scope.query_selector_all(_FIELD_SELECTOR):
        try:
            if not el.is_visible():
                continue
            if required_only:
                required = el.get_attribute("required") is not None or el.get_attribute("aria-required") == "true"
                if not required:
                    continue
            fields.append((_label_for(scope, el), el))
        except Exception:
            logger.exception("failed to inspect a form field")
    return fields


def enumerate_required_fields(scope: PageOrFrame) -> list[tuple[str, ElementHandle]]:
    """[(label, element)] for every visible, required field on the form -
    used for the bail check (only unmapped *required* fields block a
    submission; an unmapped optional field is just left blank)."""
    return _enumerate_fields(scope, required_only=True)


def enumerate_all_fields(scope: PageOrFrame) -> list[tuple[str, ElementHandle]]:
    """[(label, element)] for every visible field, required or not - used
    for filling, so optional-but-fillable fields (e.g. LinkedIn URL) still
    get populated even though their absence wouldn't block submission."""
    return _enumerate_fields(scope, required_only=False)


def find_unmapped_required_fields(scope: PageOrFrame) -> list[str]:
    return sorted({label for label, _ in enumerate_required_fields(scope) if label and not is_known_label(label)})


def _current_company(resume: ResumeDocument) -> str:
    for exp in resume.experience:
        if exp.end_date.strip().lower() == "present":
            return exp.company
    return resume.experience[0].company if resume.experience else ""


def _link_matching(resume: ResumeDocument, keyword: str) -> str:
    for link in resume.contact.links:
        if keyword in link.lower():
            return link
    return ""


def _non_linkedin_link(resume: ResumeDocument) -> str:
    for link in resume.contact.links:
        if "linkedin" not in link.lower():
            return link
    return ""


def fill_known_fields(scope: PageOrFrame, resume: ResumeDocument, resume_pdf_path: str) -> None:
    contact = resume.contact
    other_link = _non_linkedin_link(resume)
    values = {
        "first name": contact.first_name,
        "last name": contact.last_name,
        "full name": contact.full_name,
        "email": contact.email,
        "phone": contact.phone or "",
        "location": contact.location or "",
        "current company": _current_company(resume),
        "linkedin": _link_matching(resume, "linkedin"),
        "github": _link_matching(resume, "github"),
        "website": other_link,
        "portfolio": other_link,
    }

    for label, element in enumerate_all_fields(scope):
        normalized = label.strip().lower()

        if "resume" in normalized or "cv" in normalized:
            element.set_input_files(resume_pdf_path)
            continue
        if "cover letter" in normalized:
            continue  # optional, no cover-letter generation in scope

        for key, value in values.items():
            if key in normalized and value:
                _set_field(element, value)
                break


def click_if_present(scope: PageOrFrame, *text_substrings: str, timeout: int = 3000) -> bool:
    """Best-effort click on the first visible button/link whose text matches
    any of the given substrings (case-insensitive). Used for the "Apply"
    button some platforms show before revealing the actual form. Returns
    False (not an error) if nothing matched - the form may already be
    visible without that step."""
    for substring in text_substrings:
        locator = scope.get_by_role("button", name=substring, exact=False).or_(
            scope.get_by_role("link", name=substring, exact=False)
        )
        try:
            if locator.count() > 0 and locator.first.is_visible(timeout=timeout):
                locator.first.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def wait_for_confirmation(page: Page, markers: tuple[str, ...], timeout: int = 15000) -> str | None:
    """Waits briefly for the page to settle after a submit click, then
    returns the page's body text if any confirmation marker is present,
    else None."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass  # some ATS pages never go fully idle (polling widgets etc.) - fall through to a text check anyway
    body_text = page.inner_text("body")
    lowered = body_text.lower()
    if any(marker in lowered for marker in markers):
        return body_text[:2000]
    return None


def _set_field(element: ElementHandle, value: str) -> None:
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    try:
        if tag == "select":
            element.select_option(label=value)
        else:
            element.fill(value)
    except Exception:
        logger.warning("could not fill field (tag=%s) with value %r", tag, value)
