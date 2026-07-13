"""Exercises the shared Playwright form-filling engine against local HTML
fixtures (see tests/fixtures/) rather than live ATS pages, which aren't
reachable from this environment. The fixtures mimic the structural pattern
research turned up for Greenhouse/Lever/Ashby forms (labeled required
fields, an optional cover-letter/LinkedIn field, and - for Ashby - a
button that reveals the form) without depending on any real company's
exact markup.
"""

from __future__ import annotations

from pathlib import Path

from jobapply.applier import form_filler
from jobapply.resume.schema import ContactInfo, ExperienceEntry, ResumeDocument

FIXTURES_DIR = Path(__file__).parent / "fixtures"

RESUME = ResumeDocument(
    contact=ContactInfo(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="+1 555 123 4567",
        location="Remote",
        links=["https://linkedin.com/in/janedoe", "https://github.com/janedoe"],
    ),
    summary="Senior engineer.",
    experience=[
        ExperienceEntry(
            company="Acme", title="Senior Engineer", start_date="2020", end_date="present", bullets=["Did things."]
        )
    ],
)


def _fixture_url(name: str) -> str:
    return (FIXTURES_DIR / name).resolve().as_uri()


def test_enumerate_required_fields_finds_all_required(page):
    page.goto(_fixture_url("ats_form_ok.html"))
    labels = {label for label, _ in form_filler.enumerate_required_fields(page)}
    assert labels == {"First Name", "Last Name", "Email", "Phone", "Resume/CV"}


def test_find_unmapped_required_fields_empty_on_known_form(page):
    page.goto(_fixture_url("ats_form_ok.html"))
    assert form_filler.find_unmapped_required_fields(page) == []


def test_find_unmapped_required_fields_catches_custom_question(page):
    page.goto(_fixture_url("ats_form_unmapped.html"))
    assert form_filler.find_unmapped_required_fields(page) == ["Why do you want to work here?"]


def test_fill_known_fields_fills_correct_values(page, tmp_path):
    page.goto(_fixture_url("ats_form_ok.html"))
    resume_pdf = tmp_path / "resume.pdf"
    resume_pdf.write_bytes(b"%PDF-1.4 fake")

    form_filler.fill_known_fields(page, RESUME, str(resume_pdf))

    assert page.input_value("#first_name") == "Jane"
    assert page.input_value("#last_name") == "Doe"
    assert page.input_value("#email") == "jane@example.com"
    assert page.input_value("#phone") == "+1 555 123 4567"
    assert page.input_value("#linkedin") == "https://linkedin.com/in/janedoe"
    assert page.input_value("#cover_letter") == ""  # optional, deliberately left blank


def test_click_if_present_reveals_hidden_form(page):
    page.goto(_fixture_url("ats_form_reveal.html"))
    assert form_filler.click_if_present(page, "apply for this job", "apply now", "apply") is True
    form_filler.wait_for_any_field(page)
    assert form_filler.find_unmapped_required_fields(page) == []


def test_submit_flow_produces_confirmation_text(page, tmp_path):
    page.goto(_fixture_url("ats_form_ok.html"))
    resume_pdf = tmp_path / "resume.pdf"
    resume_pdf.write_bytes(b"%PDF-1.4 fake")

    form_filler.fill_known_fields(page, RESUME, str(resume_pdf))
    page.click("#submit_app")

    confirmation = form_filler.wait_for_confirmation(page, ("thank you", "received"))
    assert confirmation is not None
    assert "thank you" in confirmation.lower()


def test_wait_for_confirmation_returns_none_without_a_marker(page):
    page.goto(_fixture_url("ats_form_ok.html"))
    assert form_filler.wait_for_confirmation(page, ("some marker that never appears",), timeout=1000) is None
