#!/usr/bin/env sh
# Container entrypoint: run Alembic migrations when a real database URL is
# configured (PostgreSQL), then start the app. SQLite dev mode skips Alembic
# and relies on create_all + upgrade_schema (zero-config path).

set -e

if [ -n "$DATABASE_URL" ]; then
    echo "[migrate] DATABASE_URL set ($DATABASE_URL) - running alembic upgrade head"
    alembic upgrade head
else
    echo "[migrate] No DATABASE_URL - SQLite dev path, create_all handles schema"
fi

exec python -m a_cal.api.standalone
