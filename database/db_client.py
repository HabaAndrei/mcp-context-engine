from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator
from config_env import env_vars

from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from logger import log_error

# Database configuration via environment variables
# Set CON_MCP_DB_TYPE to "sqlite" or "postgres" (defaults to postgres)
CON_MCP_DB_TYPE = env_vars.get("CON_MCP_DB_TYPE")

# PostgreSQL configuration
DB_HOST = env_vars.get("DB_HOST")
DB_USER = env_vars.get("DB_USER")
DB_PASSWORD = env_vars.get("DB_PASSWORD")
DB_NAME = env_vars.get("DB_NAME")
DB_PORT = env_vars.get("DB_PORT")

# SQLite configuration
CON_MCP_SQLITE_PATH = env_vars.get("CON_MCP_SQLITE_PATH", "./data.db")

# Build DATABASE_URL based on CON_MCP_DB_TYPE
if CON_MCP_DB_TYPE == "sqlite":
    DATABASE_URL = f"sqlite+aiosqlite:///{CON_MCP_SQLITE_PATH}"
elif CON_MCP_DB_TYPE == "postgres":
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    log_error(" You have to add value for CON_MCP_DB_TYPE env var")

# Async database engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Session factory for async operations
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Global session context variable (thread-safe)
_session_context: ContextVar[AsyncSession | None] = ContextVar("session_context", default=None)


def get_session() -> AsyncSession | None:
    """Get the current database session from context.

    Returns None if no session is set in context.
    """
    return _session_context.get()


async def get_or_create_session() -> tuple[AsyncSession, bool]:
    """Get existing session or create a new one.

    Returns:
        tuple[AsyncSession, bool]: (session, created_new)
            - session: The AsyncSession to use
            - created_new: True if a new session was created, False if using existing
    """
    session = _session_context.get()
    if session is not None:
        return session, False

    # Create new session
    new_session = AsyncSessionLocal()
    return new_session, True


def set_session(session: AsyncSession) -> None:
    """Set the current database session in the context."""
    _session_context.set(session)


def clear_session() -> None:
    """Clear the current database session from the context."""
    _session_context.set(None)


@asynccontextmanager
async def auto_session():
    """Automatically manage database session.

    If a session exists in context, use it.
    If not, create a new one and auto-commit/rollback.

    Usage in service functions:
        async with auto_session() as session:
            # use session
            pass
    """
    existing_session = _session_context.get()

    if existing_session is not None:
        # Use existing session (we're inside a transaction)
        yield existing_session
    else:
        # Create new session for this operation
        async with AsyncSessionLocal() as session:
            # Set the session in context so nested calls can use it
            token = _session_context.set(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                # Reset the context to previous state
                _session_context.reset(token)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager for database sessions.

    Usage:
        async with session_scope() as session:
            # session is automatically set in context
            await my_database_function()  # This can use get_session()
    """
    async with AsyncSessionLocal() as session:
        set_session(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            clear_session()


async def get_db():
    """Database dependency for FastAPI routes.

    This also sets the session in the global context so service functions
    can use get_session() without needing the session passed as a parameter.
    """
    async with AsyncSessionLocal() as db:
        set_session(db)
        try:
            yield db
        finally:
            clear_session()






# Scenario 1: Standalone call
# await create_issue(...)
# → auto_session() finds NO session in context
# → creates its own session, commits immediately ✅



# Scenario 2: Transaction control
# async with session_scope():  # Sets session in context
#     await create_issue(...)  # auto_session() finds session, uses it
#     await add_comment(...)   # auto_session() finds session, uses it
# → session_scope() commits everything together ✅


# Scenario 3: is specifically for FastAPI (or similar frameworks with dependency injection). Here's where you use it
# @app.get("/issues/{issue_id}")
# async def get_issue_endpoint(
#     issue_id: str,
#     db: AsyncSession = Depends(get_db)  # ← Use it in every route
# ):
#     details = await get_issue_details(issue_id)
#     return details