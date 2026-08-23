"""Environment loading, discovery and precedence.

`EnvVars` snapshots the environment when it is first constructed, so these
tests run each case in a fresh interpreter. The module is copied into the
temporary directory first, because `.env` discovery starts from the module's
own location and walks upward - not from the working directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROBE = """
import sys
sys.path.insert(0, {root!r})
from config_env import EnvVars
print(EnvVars().get({name!r}, "<unset>"))
"""


def probe(where: Path, name: str, env_extra: dict[str, str]) -> str:
    """Import a relocated config_env in a fresh process and read one value."""
    shutil.copy(REPO_ROOT / "config_env.py", where / "config_env.py")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(PROBE).format(root=str(where), name=name),
        ],
        cwd=str(where),
        env={**os.environ, "PYTHONPATH": str(where), **env_extra},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestPrecedence:
    def test_real_environment_beats_the_env_file(self, tmp_path):
        """Regression: the .env file used to override the real environment.

        MCP clients pass configuration through an `env` block in their config.
        While the file won, a leftover .env in the checkout silently redirected
        every client to the same database whatever it had asked for.
        """
        (tmp_path / ".env").write_text("CON_MCP_SQLITE_PATH=./from_file.db\n")

        value = probe(
            tmp_path,
            "CON_MCP_SQLITE_PATH",
            {"CON_MCP_SQLITE_PATH": "/tmp/from_environment.db"},
        )

        assert value == "/tmp/from_environment.db"

    def test_env_file_supplies_values_the_environment_lacks(self, tmp_path):
        (tmp_path / ".env").write_text("CON_MCP_TEST_MARKER=from_file\n")

        assert probe(tmp_path, "CON_MCP_TEST_MARKER", {}) == "from_file"

    def test_absent_env_file_is_not_an_error(self, tmp_path):
        assert probe(tmp_path, "CON_MCP_TEST_MARKER", {}) == "<unset>"

    def test_env_file_is_found_in_a_parent_directory(self, tmp_path):
        """Discovery walks upward, so a nested module still finds the file."""
        (tmp_path / ".env").write_text("CON_MCP_TEST_MARKER=from_parent\n")
        nested = tmp_path / "nested"
        nested.mkdir()

        assert probe(nested, "CON_MCP_TEST_MARKER", {}) == "from_parent"


class TestSingleton:
    def test_repeated_construction_returns_one_instance(self):
        from config_env import EnvVars

        assert EnvVars() is EnvVars()

    def test_default_is_returned_for_unset_names(self):
        from config_env import env_vars

        assert env_vars.get("CON_MCP_DEFINITELY_NOT_SET", "fallback") == "fallback"

    def test_missing_name_without_default_is_none(self):
        from config_env import env_vars

        assert env_vars.get("CON_MCP_DEFINITELY_NOT_SET") is None
