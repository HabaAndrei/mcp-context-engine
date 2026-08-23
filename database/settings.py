"""Database connection settings.

Responsibility: turn raw environment variables into a validated SQLAlchemy URL,
failing loudly at the point of misconfiguration rather than at first use.

The previous approach built the URL at import time and left it undefined when
`CON_MCP_DB_TYPE` was absent, which surfaced as a confusing `NameError` from
deep inside the import machinery. Everything here raises `ConfigurationError`
with a message naming the variable that needs attention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config_env import env_vars

SQLITE: Final = "sqlite"
POSTGRES: Final = "postgres"

SUPPORTED_BACKENDS: Final = (SQLITE, POSTGRES)

DEFAULT_BACKEND: Final = SQLITE
DEFAULT_SQLITE_PATH: Final = "./data.db"

# Required only when the postgres backend is selected.
_POSTGRES_VARS: Final = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")


class ConfigurationError(RuntimeError):
    """Raised when environment variables do not describe a usable database."""


@dataclass(frozen=True)
class DatabaseSettings:
    """A resolved, validated description of where issues are stored."""

    backend: str
    url: str

    @property
    def is_sqlite(self) -> bool:
        return self.backend == SQLITE


def _require(name: str) -> str:
    """Read a variable that must be present and non-empty."""
    value = env_vars.get(name)
    if value is None or not str(value).strip():
        raise ConfigurationError(
            f"{name} is required when CON_MCP_DB_TYPE={POSTGRES!r}. "
            f"Set it in your .env file or the process environment."
        )
    return str(value).strip()


def build_sqlite_url(path: str) -> str:
    """Build an async SQLite URL. `:memory:` is passed through untouched."""
    if path == ":memory:":
        return "sqlite+aiosqlite:///:memory:"
    return f"sqlite+aiosqlite:///{path}"


def build_postgres_url(
    *, user: str, password: str, host: str, port: str, name: str
) -> str:
    """Build an async PostgreSQL URL from already-validated components."""
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def load_settings() -> DatabaseSettings:
    """Resolve database settings from the environment.

    Defaults to SQLite, matching README.md and .env.example. An unrecognised
    backend is an error rather than a silent fallback: quietly writing to the
    wrong database is worse than refusing to start.
    """
    backend = (
        str(env_vars.get("CON_MCP_DB_TYPE", DEFAULT_BACKEND) or "").strip().lower()
    )

    if not backend:
        backend = DEFAULT_BACKEND

    if backend not in SUPPORTED_BACKENDS:
        raise ConfigurationError(
            f"CON_MCP_DB_TYPE={backend!r} is not supported. "
            f"Expected one of: {', '.join(SUPPORTED_BACKENDS)}."
        )

    if backend == SQLITE:
        path = str(
            env_vars.get("CON_MCP_SQLITE_PATH", DEFAULT_SQLITE_PATH)
            or DEFAULT_SQLITE_PATH
        ).strip()
        return DatabaseSettings(backend=SQLITE, url=build_sqlite_url(path))

    values = {name: _require(name) for name in _POSTGRES_VARS}
    return DatabaseSettings(
        backend=POSTGRES,
        url=build_postgres_url(
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
            host=values["DB_HOST"],
            port=values["DB_PORT"],
            name=values["DB_NAME"],
        ),
    )
