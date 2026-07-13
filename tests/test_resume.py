from __future__ import annotations

from jobapply.resume.render import render_resume_pdf
from jobapply.resume.schema import ContactInfo, ExperienceEntry, ResumeDocument


def test_render_resume_pdf_produces_a_pdf_file(tmp_path, monkeypatch):
    monkeypatch.setattr("jobapply.resume.render.OUTPUT_DIR", tmp_path)
    resume = ResumeDocument(
        contact=ContactInfo(first_name="Jane", last_name="Doe", email="jane@example.com"),
        summary="Engineer.",
        skills=["Python"],
        experience=[
            ExperienceEntry(company="Acme", title="Engineer", start_date="2020", end_date="present", bullets=["Did things."])
        ],
    )
    path = render_resume_pdf(resume, job_id=42)
    assert path.endswith("job_42.pdf")
    with open(path, "rb") as f:
        assert f.read(4) == b"%PDF"
