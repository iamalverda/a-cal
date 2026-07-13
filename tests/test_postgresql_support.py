"""Tests for PostgreSQL support — URL detection, JSON type dialect awareness,
and engine configuration.

These tests verify the database abstraction layer without needing an actual
PostgreSQL instance. They check that the right engine is created based on
environment variables, and that the JSONType decorator handles both SQLite
and PostgreSQL dialects correctly.
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, String, Column, Table, MetaData

from a_cal.db.models import (
    Base,
    JSONType,
    create_engine_and_session,
    get_database_url,
    get_db_path,
)


class TestDatabaseUrlDetection:
    """Tests for DATABASE_URL environment variable handling."""

    def test_get_database_url_returns_none_when_unset(self):
        """DATABASE_URL not set → returns None."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            assert get_database_url() is None

    def test_get_database_url_returns_value_when_set(self):
        """DATABASE_URL set → returns the URL string."""
        test_url = "postgresql://user:pass@localhost:5432/acal"
        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            assert get_database_url() == test_url

    def test_get_db_path_respects_env_override(self):
        """A_CAL_DB_PATH env var overrides the default path."""
        with patch.dict(os.environ, {"A_CAL_DB_PATH": "/tmp/test-acal.db"}):
            assert get_db_path() == "/tmp/test-acal.db"


class TestEngineCreation:
    """Tests for create_engine_and_session with different configurations."""

    def test_in_memory_sqlite(self):
        """In-memory SQLite uses StaticPool for connection sharing."""
        engine, session_local = create_engine_and_session(":memory:")
        assert engine.dialect.name == "sqlite"
        # Verify tables are created
        from a_cal.db.models import SubAccount
        with session_local() as session:
            # Can query without error (table exists)
            session.query(SubAccount).all()
        engine.dispose()

    def test_explicit_sqlite_path(self):
        """Explicit SQLite file path creates a file-backed database."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine, _ = create_engine_and_session(db_path)
            assert engine.dialect.name == "sqlite"
            assert os.path.exists(db_path)
            engine.dispose()
        finally:
            os.unlink(db_path)

    def test_database_url_takes_priority_over_sqlite_default(self):
        """When DATABASE_URL is set, it's used instead of SQLite default."""
        # We can't actually connect to PostgreSQL in tests, but we can
        # verify the URL is picked up by checking the engine URL.
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake:fake@localhost:5432/fake"}):
            with patch("a_cal.db.models.create_engine") as mock_create:
                mock_engine = MagicMock()
                mock_engine.dialect.name = "postgresql"
                mock_create.return_value = mock_engine
                engine, _ = create_engine_and_session()
                # Verify create_engine was called with the PostgreSQL URL
                call_args = mock_create.call_args
                assert "postgresql" in str(call_args)

    def test_sqlite_fallback_when_no_database_url(self):
        """Without DATABASE_URL, falls back to SQLite (in-memory for tests)."""
        with patch.dict(os.environ, {"A_CAL_DB_PATH": ":memory:"}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            engine, session_local = create_engine_and_session()
            assert engine.dialect.name == "sqlite"
            engine.dispose()

    def test_pool_pre_ping_for_external_databases(self):
        """External databases get pool_pre_ping=True for connection health checks."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake:fake@localhost:5432/fake"}):
            with patch("a_cal.db.models.create_engine") as mock_create:
                mock_engine = MagicMock()
                mock_engine.dialect.name = "postgresql"
                mock_create.return_value = mock_engine
                create_engine_and_session()
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs.get("pool_pre_ping") is True


class TestJSONType:
    """Tests for the dialect-aware JSONType decorator."""

    def test_json_type_serializes_on_sqlite(self):
        """JSONType serializes dicts to JSON strings on SQLite."""
        engine = create_engine("sqlite://")
        metadata = MetaData()
        test_table = Table(
            "test_json", metadata,
            Column("id", String(10), primary_key=True),
            Column("data", JSONType),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(test_table.insert(), {"id": "1", "data": {"key": "value"}})
            result = conn.execute(test_table.select()).fetchone()
            # On SQLite, the stored value comes back as a parsed dict
            assert result.data == {"key": "value"}

    def test_json_type_handles_none(self):
        """JSONType handles None values correctly."""
        engine = create_engine("sqlite://")
        metadata = MetaData()
        test_table = Table(
            "test_json_null", metadata,
            Column("id", String(10), primary_key=True),
            Column("data", JSONType),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(test_table.insert(), {"id": "1", "data": None})
            result = conn.execute(test_table.select()).fetchone()
            assert result.data is None

    def test_json_type_handles_lists(self):
        """JSONType handles list values."""
        engine = create_engine("sqlite://")
        metadata = MetaData()
        test_table = Table(
            "test_json_list", metadata,
            Column("id", String(10), primary_key=True),
            Column("tags", JSONType),
        )
        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(test_table.insert(), {"id": "1", "tags": ["a", "b", "c"]})
            result = conn.execute(test_table.select()).fetchone()
            assert result.tags == ["a", "b", "c"]

    def test_json_type_load_dialect_impl_sqlite(self):
        """load_dialect_impl returns Text for SQLite."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect
        jt = JSONType()
        dialect = SQLiteDialect()
        impl = jt.load_dialect_impl(dialect)
        # Should return a Text type for SQLite
        assert impl is not None


class TestAlembicConfig:
    """Tests for Alembic migration configuration."""

    def test_alembic_ini_exists(self):
        """alembic.ini file exists at project root."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert os.path.exists(os.path.join(project_root, "alembic.ini"))

    def test_alembic_env_exists(self):
        """alembic/env.py file exists."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert os.path.exists(os.path.join(project_root, "alembic", "env.py"))

    def test_migration_0001_exists(self):
        """Initial migration 0001 exists."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        versions_dir = os.path.join(project_root, "alembic", "versions")
        files = os.listdir(versions_dir)
        assert any("0001" in f for f in files)

    def test_migration_0002_exists(self):
        """Additional tables migration 0002 exists."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        versions_dir = os.path.join(project_root, "alembic", "versions")
        files = os.listdir(versions_dir)
        assert any("0002" in f for f in files)

    def test_env_py_imports_base_metadata(self):
        """env.py imports Base.metadata as the migration target."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(project_root, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "from a_cal.db.models import Base" in content
        assert "target_metadata = Base.metadata" in content

    def test_env_py_reads_database_url(self):
        """env.py reads DATABASE_URL from environment."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(project_root, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "DATABASE_URL" in content


class TestDockerAndEnvConfig:
    """Tests for Docker Compose and .env.example configuration."""

    def test_docker_compose_has_postgres_profile(self):
        """docker-compose.yml includes a postgres service with profile."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        compose_path = os.path.join(project_root, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()
        assert "postgres" in content
        assert "profile" in content.lower()
        assert "DATABASE_URL" in content

    def test_docker_compose_has_postgres_volume(self):
        """docker-compose.yml defines a postgres data volume."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        compose_path = os.path.join(project_root, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()
        assert "a-cal-postgres" in content

    def test_env_example_mentions_database_url(self):
        """.env.example documents DATABASE_URL for PostgreSQL."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(project_root, ".env.example")
        with open(env_path) as f:
            content = f.read()
        assert "DATABASE_URL" in content
        assert "postgresql" in content

    def test_dockerfile_installs_postgres_extras(self):
        """Dockerfile.backend installs postgres and migrations extras."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dockerfile_path = os.path.join(project_root, "Dockerfile.backend")
        with open(dockerfile_path) as f:
            content = f.read()
        assert "postgres" in content
        assert "migrations" in content
        assert "libpq-dev" in content  # PostgreSQL dev headers

    def test_pyproject_has_postgres_extra(self):
        """pyproject.toml includes postgres optional dependency group."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pyproject_path = os.path.join(project_root, "pyproject.toml")
        with open(pyproject_path) as f:
            content = f.read()
        assert "psycopg2-binary" in content
        assert 'postgres = [' in content

    def test_pyproject_has_migrations_extra(self):
        """pyproject.toml includes migrations optional dependency group."""
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pyproject_path = os.path.join(project_root, "pyproject.toml")
        with open(pyproject_path) as f:
            content = f.read()
        assert "alembic" in content
        assert 'migrations = [' in content
