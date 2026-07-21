"""Runtime configuration, backed by the `settings` DB table.

Every configurable value has a hardcoded default here (mirrored in
config.yaml.example for documentation). The Settings page and /setup wizard
read/write rows in the `settings` table; anything without a row falls back
to its default below, so a brand-new database is always in a valid,
if unconfigured, state.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from jobapply.db.models import Setting, User
from jobapply.db.session import session_scope


@dataclass(frozen=True)
class SettingSpec:
    default: str | None
    is_secret: bool = False


SETTING_SPECS: dict[str, SettingSpec] = {
    "llm.profile": SettingSpec("gemini"),
    "llm.gemini.base_url": SettingSpec("https://generativelanguage.googleapis.com/v1beta/openai/"),
    "llm.gemini.api_key": SettingSpec(None, is_secret=True),
    "llm.gemini.model_finder": SettingSpec("gemini-2.5-flash-lite"),
    "llm.gemini.model_tailor": SettingSpec("gemini-2.5-flash"),
    "llm.gemini.model_fabrication_check": SettingSpec("gemini-2.5-flash"),
    "llm.gemini.model_gap_advisor": SettingSpec("gemini-2.5-flash"),
    "llm.local.base_url": SettingSpec("http://localhost:8080/v1"),
    "llm.local.api_key": SettingSpec("not-needed", is_secret=True),
    "llm.local.model_finder": SettingSpec("local-model"),
    "llm.local.model_tailor": SettingSpec("local-model"),
    "llm.local.model_fabrication_check": SettingSpec("local-model"),
    "llm.local.model_gap_advisor": SettingSpec("local-model"),
    "sources.jsearch.enabled": SettingSpec("true"),
    "sources.jsearch.api_key": SettingSpec(None, is_secret=True),
    "sources.jsearch.host": SettingSpec("jsearch.p.rapidapi.com"),
    "sources.jsearch.query": SettingSpec("software engineer remote"),
    "sources.jsearch.location": SettingSpec(""),
    "sources.jsearch.date_posted": SettingSpec("week"),
    "sources.jsearch.remote_jobs_only": SettingSpec("true"),
    "sources.greenhouse.enabled": SettingSpec("true"),
    "sources.greenhouse.boards": SettingSpec(""),  # comma-separated board tokens
    "sources.lever.enabled": SettingSpec("true"),
    "sources.lever.boards": SettingSpec(""),  # comma-separated Lever site names
    "sources.ashby.enabled": SettingSpec("true"),
    "sources.ashby.boards": SettingSpec(""),  # comma-separated Ashby job-board names
    "scoring.fit_score_threshold": SettingSpec("70"),
    "notify.ntfy.base_url": SettingSpec("https://ntfy.sh"),
    "notify.ntfy.topic": SettingSpec(None, is_secret=True),
    "notify.ntfy.auth_token": SettingSpec(None, is_secret=True),
    "dashboard.base_url": SettingSpec("http://localhost:8000"),
    "scheduler.finder_cron": SettingSpec("0 8-22/3 * * *"),
    "scheduler.gap_advisor_cron": SettingSpec("0 9 * * 1"),  # weekly, Monday 9am
    "scheduler.timezone": SettingSpec("UTC"),
    "resume.master_path": SettingSpec("resume/master_resume.yaml"),
    "playwright.headless": SettingSpec("true"),
    "playwright.screenshot_dir": SettingSpec("data/evidence"),
}


def is_secret(key: str) -> bool:
    spec = SETTING_SPECS.get(key)
    return bool(spec and spec.is_secret)


def get_setting(key: str) -> str | None:
    spec = SETTING_SPECS.get(key)
    default = spec.default if spec else None
    with session_scope() as session:
        row = session.scalar(select(Setting).where(Setting.key == key))
        if row is None or row.value is None:
            return default
        return row.value


def get_bool(key: str) -> bool:
    return (get_setting(key) or "").strip().lower() in {"1", "true", "yes", "on"}


def get_int(key: str) -> int | None:
    value = get_setting(key)
    return int(value) if value is not None and value != "" else None


def get_list(key: str) -> list[str]:
    value = get_setting(key) or ""
    return [item.strip() for item in value.split(",") if item.strip()]


def set_setting(key: str, value: str | None) -> None:
    if key not in SETTING_SPECS:
        raise KeyError(f"Unknown setting key: {key}")
    with session_scope() as session:
        row = session.scalar(select(Setting).where(Setting.key == key))
        if row is None:
            row = Setting(key=key, is_secret=SETTING_SPECS[key].is_secret)
            session.add(row)
        row.value = value
        row.is_secret = SETTING_SPECS[key].is_secret


def get_all_settings() -> dict[str, str | None]:
    return {key: get_setting(key) for key in SETTING_SPECS}


def llm_profile_config(profile: str | None = None) -> dict[str, str]:
    """base_url/api_key/model triple for the given (or active) LLM profile."""
    profile = profile or get_setting("llm.profile") or "gemini"
    prefix = f"llm.{profile}"
    return {
        "profile": profile,
        "base_url": get_setting(f"{prefix}.base_url") or "",
        "api_key": get_setting(f"{prefix}.api_key") or "",
        "model_finder": get_setting(f"{prefix}.model_finder") or "",
        "model_tailor": get_setting(f"{prefix}.model_tailor") or "",
        "model_fabrication_check": get_setting(f"{prefix}.model_fabrication_check") or "",
        "model_gap_advisor": get_setting(f"{prefix}.model_gap_advisor") or "",
    }


def has_users() -> bool:
    with session_scope() as session:
        return session.scalar(select(User.id).limit(1)) is not None


def is_setup_complete() -> bool:
    """Gate for redirecting to /setup: is there enough config to run the pipeline?"""
    if not has_users():
        return False
    llm = llm_profile_config()
    if not llm["api_key"] and llm["profile"] == "gemini":
        return False
    if not get_setting("notify.ntfy.topic"):
        return False
    any_source = (
        (get_bool("sources.jsearch.enabled") and get_setting("sources.jsearch.api_key"))
        or get_bool("sources.greenhouse.enabled")
        or get_bool("sources.lever.enabled")
        or get_bool("sources.ashby.enabled")
    )
    return bool(any_source)
