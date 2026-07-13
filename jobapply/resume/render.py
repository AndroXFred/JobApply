from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from jobapply.resume.schema import ResumeDocument

TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path("data/resumes")

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def render_resume_pdf(resume: ResumeDocument, job_id: int) -> str:
    template = _env.get_template("resume.html.jinja")
    html_content = template.render(resume=resume)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"job_{job_id}.pdf"
    HTML(string=html_content, base_url=str(TEMPLATE_DIR)).write_pdf(str(output_path))
    return str(output_path)
