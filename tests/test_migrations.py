"""Migration parity tests.

The Postgres entrypoint (``scripts/migrate-and-start.sh``) relies on
``alembic upgrade head`` alone to build the schema: ``create_all`` only
creates *missing tables* (it never alters existing ones) and
``upgrade_schema`` only patches a hand-maintained column list. Any model
column absent from the migration chain therefore crashes ORM queries on a
fresh Postgres deploy while remaining invisible to the rest of the test
suite, which builds its schema via ``create_all`` on in-memory SQLite.

These tests run the real migration chain against a throwaway SQLite file
and diff the result against ``Base.metadata``, and compile the chain for
PostgreSQL in offline mode to catch dialect-invalid DDL (e.g. integer
server defaults on boolean columns, which PostgreSQL rejects).
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config(url: str, output_buffer: io.StringIO | None = None) -> Config:
    """Build an alembic Config pinned to this repo, targeting ``url``."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"), output_buffer=output_buffer)
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_alembic_head_matches_model_columns(tmp_path, monkeypatch):
    """``alembic upgrade head`` on a fresh DB yields every model table/column."""
    from a_cal.db.models import Base

    db_path = tmp_path / "migration-parity.db"
    url = f"sqlite:///{db_path}"
    # alembic/env.py prefers DATABASE_URL over the ini url — pin both.
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic_config(url), "head")

    conn = sqlite3.connect(db_path)
    try:
        db_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } - {"alembic_version"}

        missing_tables = sorted(set(Base.metadata.tables) - db_tables)
        assert not missing_tables, f"tables missing from migrations: {missing_tables}"

        # Extra legacy columns in migrations are tolerated (nullable leftovers);
        # missing model columns are not — the ORM selects every mapped column.
        drift: dict[str, list[str]] = {}
        for table_name, table in Base.metadata.tables.items():
            model_cols = {col.name for col in table.columns}
            db_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
            missing = sorted(model_cols - db_cols)
            if missing:
                drift[table_name] = missing
        assert not drift, f"model columns missing after alembic upgrade head: {drift}"
    finally:
        conn.close()


def test_orm_operations_work_on_migrated_schema(tmp_path, monkeypatch):
    """Every model the app writes at runtime round-trips on a migrated DB.

    Column-name parity alone misses two failure classes this test catches:
    legacy NOT NULL columns the ORM never sets (insert -> IntegrityError),
    and constraints that reject legitimate rows (the original 0001 unique
    constraint refused a user's second non-main sub-account).
    """
    from datetime import datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from a_cal.db.models import (
        BookingDB,
        CalendarEvent,
        EventTypeDB,
        ProviderConnection,
        SubAccount,
        Team,
        TeamMember,
        User,
        WebhookConfig,
    )

    db_path = tmp_path / "migration-orm.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic_config(url), "head")

    # Local engine on purpose: the app's module-level engine singleton is
    # shared by the rest of the suite and must not be rebound.
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    start = datetime(2026, 8, 1, 10, 0)
    try:
        session.add(User(id="u-1", email="parity@test.local", password_hash="x"))
        session.add(SubAccount(id="sa-1", user_id="u-1", name="Main", is_main=True))
        # Two non-main sub-accounts for one user — rejected by the original
        # 0001 (user_id, is_main) unique constraint.
        session.add(SubAccount(id="sa-2", user_id="u-1", name="Work"))
        session.add(SubAccount(id="sa-3", user_id="u-1", name="Personal"))
        session.add(ProviderConnection(
            id="pc-1", sub_account_id="sa-2",
            provider_type="google_calendar", provider_account_id="acct",
        ))
        session.add(CalendarEvent(
            id="ev-1", user_id="u-1", provider_event_id="pev-1",
            provider_type="google_calendar", title="Kickoff",
            start=start, end=start + timedelta(hours=1),
        ))
        session.add(EventTypeDB(
            id="et-1", user_id="u-1", title="Intro", slug="intro",
            duration_minutes=30,
        ))
        session.add(BookingDB(
            id="bk-1", event_type_id="et-1", user_id="u-1",
            attendee_name="A", attendee_email="a@test.local",
            start_time=start, end_time=start + timedelta(minutes=30),
        ))
        session.add(Team(id="team-1", user_id="u-1", name="Ops"))
        session.add(TeamMember(id="tm-1", team_id="team-1", email="m@test.local"))
        session.add(WebhookConfig(
            id="wh-1", user_id="u-1", url="https://example.invalid/hook",
        ))
        session.commit()

        assert session.query(SubAccount).filter(SubAccount.user_id == "u-1").count() == 3
        assert session.query(EventTypeDB).filter(EventTypeDB.user_id == "u-1").count() == 1
        assert session.query(WebhookConfig).filter(WebhookConfig.user_id == "u-1").count() == 1
    finally:
        session.close()
        engine.dispose()


def test_migration_chain_compiles_for_postgresql(monkeypatch):
    """The chain renders valid PostgreSQL DDL in offline mode.

    Guards the dialect trap that SQLite-only testing cannot see: PostgreSQL
    rejects integer server defaults on BOOLEAN columns (``DEFAULT 1``), so a
    migration written that way crashes ``alembic upgrade head`` on Postgres
    even though it applies cleanly on SQLite.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    buf = io.StringIO()
    command.upgrade(
        _alembic_config("postgresql://user:pass@localhost/unused", output_buffer=buf),
        "head",
        sql=True,  # offline mode: compile only, no connection
    )
    sql = buf.getvalue()
    assert "CREATE TABLE" in sql, "offline compile produced no DDL"

    bad_boolean_defaults = [
        line.strip()
        for line in sql.splitlines()
        if "BOOLEAN" in line.upper()
        and ("DEFAULT 1" in line.upper() or "DEFAULT 0" in line.upper())
    ]
    assert not bad_boolean_defaults, (
        "integer server defaults on BOOLEAN columns are invalid on PostgreSQL: "
        f"{bad_boolean_defaults}"
    )
