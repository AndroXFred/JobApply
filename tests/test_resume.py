from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from jobapply import config
from jobapply.resume import loader
from jobapply.resume.render import render_resume_pdf
from jobapply.resume.schema import ContactInfo, ExperienceEntry, ResumeDocument
from jobapply.web.routers.resume import validate_and_save

VALID_YAML = """
contact:
  first_name: Jane
  last_name: Doe
  email: jane@example.com
summary: Senior engineer.
skills: [Python]
experience:
  - company: Acme
    title: Engineer
    start_date: "2020"
    end_date: present
    bullets: ["Did things."]
"""


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


def test_resume_exists_false_then_true_after_write(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    assert loader.resume_exists() is False

    loader.write_master_resume_yaml(VALID_YAML)
    assert loader.resume_exists() is True
    assert loader.load_master_resume().contact.first_name == "Jane"


def test_write_master_resume_yaml_rejects_invalid_yaml(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    with pytest.raises(yaml.YAMLError):
        loader.write_master_resume_yaml("contact: [unclosed")
    assert loader.resume_exists() is False  # never wrote a broken file


def test_write_master_resume_yaml_rejects_schema_violation(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    with pytest.raises(ValidationError):
        loader.write_master_resume_yaml("contact:\n  first_name: Jane\nsummary: Missing required fields")
    assert loader.resume_exists() is False


def test_validate_and_save_returns_errors_for_bad_yaml(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    errors = validate_and_save("contact: [unclosed")
    assert errors
    assert "Invalid YAML" in errors[0]


def test_validate_and_save_returns_errors_for_missing_fields(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    errors = validate_and_save("contact:\n  first_name: Jane\nsummary: hi")
    assert any("last_name" in e or "email" in e for e in errors)


def test_validate_and_save_succeeds_and_persists(temp_db, tmp_path):
    config.set_setting("resume.master_path", str(tmp_path / "master_resume.yaml"))
    errors = validate_and_save(VALID_YAML)
    assert errors == []
    assert loader.load_master_resume().contact.email == "jane@example.com"
