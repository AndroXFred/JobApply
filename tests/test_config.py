from __future__ import annotations

from jobapply import config


def test_defaults_before_any_row_exists(temp_db):
    assert config.get_setting("scoring.fit_score_threshold") == "70"
    assert config.get_int("scoring.fit_score_threshold") == 70
    assert config.get_bool("sources.greenhouse.enabled") is True
    assert config.get_setting("llm.gemini.api_key") is None


def test_set_and_get_roundtrip(temp_db):
    config.set_setting("scoring.fit_score_threshold", "85")
    assert config.get_int("scoring.fit_score_threshold") == 85

    config.set_setting("sources.greenhouse.boards", "acme, examplecorp ,  ")
    assert config.get_list("sources.greenhouse.boards") == ["acme", "examplecorp"]


def test_is_setup_complete_requires_user_llm_key_and_ntfy(temp_db):
    assert config.is_setup_complete() is False

    from jobapply.web.auth import create_user

    create_user(email="a@b.com", display_name="A", password="x")
    assert config.is_setup_complete() is False  # still missing llm key + ntfy topic + a source

    config.set_setting("llm.gemini.api_key", "fake-key")
    config.set_setting("notify.ntfy.topic", "topic")
    config.set_setting("sources.greenhouse.boards", "acme")
    assert config.is_setup_complete() is True


def test_unknown_setting_key_raises(temp_db):
    import pytest

    with pytest.raises(KeyError):
        config.set_setting("not.a.real.key", "x")
