"""Tiny migration runner.

0001_init creates the full schema from the current SQLAlchemy models (kept
in sync with models.py automatically, rather than hand-duplicated in SQL).
Future schema changes should add a new numbered migration function to
MIGRATIONS and a corresponding ALTER/CREATE statement, so the history stays
linear and re-runnable.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from jobapply.db.models import Base
from jobapply.db.session import get_engine


def _migration_0001_init(conn: Connection) -> None:
    Base.metadata.create_all(bind=conn)


def _migration_0002_pipeline_runs(conn: Connection) -> None:
    # create_all only creates tables that don't yet exist, so re-running it
    # after adding PipelineRun to models.py picks up just that new table on
    # a database that already ran 0001_init - existing tables are untouched.
    Base.metadata.create_all(bind=conn)


MIGRATIONS: list[tuple[str, callable]] = [
    ("0001_init", _migration_0001_init),
    ("0002_pipeline_runs", _migration_0002_pipeline_runs),
]


def run_migrations() -> list[str]:
    """Apply any migrations not yet recorded. Returns names of migrations applied."""
    engine = get_engine()
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
        )
        already = {row[0] for row in conn.execute(text("SELECT name FROM schema_migrations"))}
        for name, fn in MIGRATIONS:
            if name in already:
                continue
            fn(conn)
            conn.execute(text("INSERT INTO schema_migrations (name) VALUES (:name)"), {"name": name})
            applied.append(name)
    return applied
