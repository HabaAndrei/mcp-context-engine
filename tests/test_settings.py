"""Configuration resolution and its failure modes."""

from __future__ import annotations

import pytest

from database import settings as settings_module
from database.settings import ConfigurationError, load_settings


class StubEnv:
    """Stand-in for the env_vars singleton, which snapshots os.environ once."""

    def __init__(self, values: dict[str, str]):
        self._values = values

    def get(self, name, default=None):
        return self._values.get(name, default)


@pytest.fixture
def env(monkeypatch):
    def apply(values: dict[str, str]):
        monkeypatch.setattr(settings_module, "env_vars", StubEnv(values))

    return apply


class TestBackendSelection:
    def test_defaults_to_sqlite(self, env):
        """README and .env.example both promise SQLite as the default."""
        env({})
        assert load_settings().backend == "sqlite"

    def test_default_sqlite_path_is_used(self, env):
        env({"CON_MCP_DB_TYPE": "sqlite"})
        assert load_settings().url == "sqlite+aiosqlite:///./data.db"

    def test_sqlite_path_is_honoured(self, env):
        env({"CON_MCP_DB_TYPE": "sqlite", "CON_MCP_SQLITE_PATH": "/tmp/board.db"})
        assert load_settings().url == "sqlite+aiosqlite:////tmp/board.db"

    def test_backend_is_case_insensitive(self, env):
        env({"CON_MCP_DB_TYPE": "SQLite"})
        assert load_settings().backend == "sqlite"

    def test_unknown_backend_is_refused(self, env):
        """Silently writing to the wrong database is worse than not starting.

        Previously an unrecognised value left DATABASE_URL undefined and the
        module raised NameError at import.
        """
        env({"CON_MCP_DB_TYPE": "mysql"})
        with pytest.raises(ConfigurationError, match="not supported"):
            load_settings()


class TestPostgres:
    def test_full_configuration_builds_an_async_url(self, env):
        env(
            {
                "CON_MCP_DB_TYPE": "postgres",
                "DB_USER": "postgres",
                "DB_PASSWORD": "secret",
                "DB_HOST": "localhost",
                "DB_PORT": "5432",
                "DB_NAME": "context",
            }
        )
        assert load_settings().url == (
            "postgresql+asyncpg://postgres:secret@localhost:5432/context"
        )

    @pytest.mark.parametrize(
        "missing", ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]
    )
    def test_each_missing_variable_is_named(self, env, missing):
        values = {
            "CON_MCP_DB_TYPE": "postgres",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_NAME": "context",
        }
        del values[missing]
        env(values)

        with pytest.raises(ConfigurationError, match=missing):
            load_settings()

    def test_blank_variable_counts_as_missing(self, env):
        env(
            {
                "CON_MCP_DB_TYPE": "postgres",
                "DB_USER": "   ",
                "DB_PASSWORD": "secret",
                "DB_HOST": "localhost",
                "DB_PORT": "5432",
                "DB_NAME": "context",
            }
        )
        with pytest.raises(ConfigurationError, match="DB_USER"):
            load_settings()
