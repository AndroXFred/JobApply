# JobApply

A personal remote-job pipeline: finds and scores job postings against your
resume, tailors your resume per job, and — only after you approve it via a
push notification — submits the application. Everything is tracked in a
local dashboard.

Pipeline:

1. **Agent 1 (Finder/Evaluator)** — pulls postings from JSearch (RapidAPI)
   plus direct Greenhouse/Lever/Ashby company boards, scores fit against
   your resume, flags scam/ghost-job postings.
2. **Agent 2 (Tailor) + Agent 2b (Resume Auditor)** — tailors your resume
   for a job above the fit threshold, then a separate LLM call verifies no
   claim was fabricated before it's ever shown to you.
3. **Approval gate** — a push notification (via [ntfy](https://ntfy.sh))
   links to the dashboard; nothing is submitted until you tap Approve there.
4. **Agent 3 (Applier)** — submits the approved application via Playwright,
   scoped to Greenhouse/Lever/Ashby ATS platforms, and saves a confirmation
   screenshot.

The LLM layer targets any OpenAI-compatible endpoint, so it runs against
Gemini today and swaps to a local model (e.g. `llama-server` on an Intel
Arc GPU) later with a config change, not a code change.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
python -m jobapply.cli migrate
python -m jobapply.cli serve
```

Open `http://localhost:8000` and complete the `/setup` wizard (API keys,
job boards, fit threshold, schedule). Nothing runs until that's done.

Add your master resume on the **Resume** page - either paste/edit it as
YAML directly, or upload a `.docx`/`.pdf` and it'll be transcribed in for
you to review before saving (nothing is saved automatically; you always
get a chance to check it first, since this file is the ground truth Agent
2b checks every tailored resume against).

## Locked out?

There's no email-based password reset (this is a single-user local app, no
SMTP setup needed) - reset directly against the database instead:

```bash
python -m jobapply.cli list-users        # see your account's email
python -m jobapply.cli reset-password --email you@example.com
```

## Development

```bash
pytest
ruff check .
```

SQLite is the source of truth, all configuration lives in the database and
is edited through the web UI (not hand-edited YAML), and each pipeline
stage is independently runnable via `python -m jobapply.cli <command>` for
testing.
