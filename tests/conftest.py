"""Shared test fixtures.

Each test runs against its own SQLite database created from the SQLAlchemy
metadata, so cases are fully isolated and the suite needs no server, no
migration run and no cleanup.

A file under tmp_path is used rather than `:memory:`. An in-memory SQLite
database belongs to a single connection, so the moment the pool hands out a
second one the schema appears to vanish - an easy way to spend an afternoon
debugging the harness instead of the code.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from database import db_client
from database.models.__utils__ import Base


@pytest_asyncio.fixture
async def db(tmp_path):
    """Point the process at a fresh database and create the schema."""
    db_client.configure(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

    engine = db_client.get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield db_client

    await db_client.dispose_engine()


@pytest.fixture
def anyio_backend():
    return "asyncio"
