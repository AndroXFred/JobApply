from __future__ import annotations

import pytest


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    import jobapply.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None

    from jobapply.db.migrate import run_migrations

    run_migrations()
    yield db_path

    session_module._engine = None
    session_module._SessionLocal = None
