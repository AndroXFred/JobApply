from __future__ import annotations

from jobapply import config
from jobapply.db.models import Job
from jobapply.notify import ntfy


def _job() -> Job:
    return Job(id=1, source="greenhouse", external_id="1", company="Acme", title="Engineer", url="https://x", raw_json={})


def test_publish_skips_when_no_topic_configured(temp_db, monkeypatch):
    calls = []
    monkeypatch.setattr(ntfy.httpx, "post", lambda *a, **k: calls.append((a, k)))
    ntfy.publish(_job())
    assert calls == []


def test_publish_sends_view_action_no_embedded_auth(temp_db, monkeypatch):
    config.set_setting("notify.ntfy.topic", "my-topic")
    config.set_setting("dashboard.base_url", "https://jobapply.example.com")

    calls = []
    monkeypatch.setattr(ntfy.httpx, "post", lambda url, content=None, headers=None, timeout=None: calls.append((url, headers)))

    ntfy.publish(_job(), fit_score=88)

    assert len(calls) == 1
    url, headers = calls[0]
    assert url == "https://ntfy.sh/my-topic"
    assert headers["Click"] == "https://jobapply.example.com/jobs/1"
    assert "view" in headers["Actions"]
    assert "https://jobapply.example.com/jobs/1" in headers["Actions"]
    # no bearer/approve action embedded when no self-hosted auth token is configured
    assert "Authorization" not in headers


def test_publish_includes_authorization_header_for_self_hosted_ntfy(temp_db, monkeypatch):
    config.set_setting("notify.ntfy.topic", "my-topic")
    config.set_setting("notify.ntfy.auth_token", "secret-token")

    calls = []
    monkeypatch.setattr(ntfy.httpx, "post", lambda url, content=None, headers=None, timeout=None: calls.append(headers))

    ntfy.publish(_job())
    assert calls[0]["Authorization"] == "Bearer secret-token"
