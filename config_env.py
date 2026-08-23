"""Environment variable access.

Loads a `.env` file once, then serves values from a snapshot taken at import.

Precedence: **the real environment wins over the `.env` file.** `.env` supplies
defaults for local development; anything explicitly exported by the process
that launched us is a deliberate choice and must not be silently overridden.
This matters most for MCP clients, which pass configuration through an `env`
block in their config file - with the precedence reversed, a leftover `.env` in
the checkout would quietly redirect every client to the same database.
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv


class EnvVars:
    """Process-wide, thread-safe view of the environment.

    A snapshot rather than a live view of `os.environ`, so configuration cannot
    change under a running server halfway through a request.
    """

    _instance: EnvVars | None = None
    _lock = Lock()

    def __new__(cls) -> EnvVars:
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        env_file = self._find_env_file()
        if env_file is not None:
            # override=False: values already exported by the parent process
            # take precedence over the file.
            load_dotenv(env_file, override=False)

        self._envs = dict(os.environ)
        self._env_file = env_file

    @staticmethod
    def _find_env_file() -> Path | None:
        """Search upward from this module for a `.env` file."""
        current = Path(__file__).resolve().parent
        while True:
            candidate = current / ".env"
            if candidate.exists():
                return candidate
            if current == current.parent:  # filesystem root
                return None
            current = current.parent

    @property
    def env_file(self) -> Path | None:
        """The `.env` that was loaded, or None if there was none."""
        return self._env_file

    def get(self, name: str, default=None):
        """Return an environment variable, or `default` if it is not set."""
        return self._envs.get(name, default)


#: Import this rather than constructing EnvVars yourself.
env_vars = EnvVars()
