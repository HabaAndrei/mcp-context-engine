# Context MCP - AI Context Engine & Project Management Server

A powerful Model Context Protocol (MCP) server that acts as a **context engine** for AI assistants, enabling them to maintain persistent task tracking across complex, multi-step workflows. Built with FastMCP, this server provides comprehensive tools for creating, managing, and organizing tasks, epics, and issues with support for dependencies, labels, comments, and hierarchical structures.

## Why This Is a Context Engine for AI

### The Problem: AI Memory & Tool Call Complexity

When AI assistants handle complex tasks, they face a critical challenge: **maintaining context across multiple tool calls and message exchanges**. As conversations grow longer and involve numerous tool invocations, AI models can:

- Lose track of which tasks are complete vs pending
- Forget dependencies between different steps
- Miss critical subtasks in multi-step workflows
- Struggle to resume work after context switches or conversation breaks

### The Solution: Persistent Context Through Structured Task Management

This MCP server solves these problems by providing AI assistants with a **persistent, external memory system** for task tracking. Instead of relying solely on conversation history, the AI can:

1. **Externalize Task State**: Store tasks, their status, dependencies, and relationships in a structured database
2. **Track Progress Persistently**: Query what's done, what's in progress, and what's blocked—even across conversation boundaries
3. **Manage Complexity**: Break down complex workflows into hierarchical structures (epics → tasks → subtasks)
4. **Maintain Context**: Use labels, comments, and events to preserve decision-making context and rationale
5. **Navigate Dependencies**: Understand what must be done before other tasks can proceed

### Real-World Example

Consider an AI helping you build a new authentication system:

**Without Context Engine:**
```
AI: I'll implement login, registration, and password reset.
[Makes several tool calls]
User: [30 minutes later] What's left to do?
AI: Let me check the conversation history... I think I did login but I'm not sure about the tests...
```

**With Context Engine:**
```
AI: I'll create an epic for authentication with child tasks.
[Creates epic #1 with children: #1.1 login, #1.2 registration, #1.3 password-reset, #1.4 tests]
[Marks #1.1 complete, #1.2 in_progress]
User: [30 minutes later] What's left to do?
AI: [Queries issues] You have #1.2 (registration) in progress, #1.3 and #1.4 pending.
```

The AI maintains perfect context through the database, not just memory.

### How It Helps in Tool Call Chains

When executing complex workflows with multiple tool calls:

- **Before each step**: AI queries pending tasks to know what to do next
- **During execution**: AI updates issue status and adds comments about decisions
- **After completion**: AI marks tasks complete and records outcomes
- **On blockers**: AI adds dependencies to track what's blocking what
- **Across sessions**: AI can resume exactly where it left off by querying issue state

This transforms the AI from a stateless responder into a **stateful project manager** that maintains perfect awareness of complex, multi-step workflows.

## Features

- **Issue Management**: Create, update, claim, and close issues with full lifecycle tracking
- **Hierarchical Organization**: Support for epics, parent-child relationships, and subtasks
- **Dependencies**: Manage complex relationships (blocks, parent-child, related, duplicates, supersedes)
- **Labels & Tags**: Flexible labeling system for categorization
- **Comments & Events**: Track discussions and custom event logs
- **Priority System**: P0-P4 priority levels for task organization
- **Status Tracking**: Monitor issue progress through various states
- **Time Estimation**: Track estimated and actual time for tasks
- **Assignee Management**: Assign issues to team members
- **Dual Database Support**: Choose between SQLite (development) or PostgreSQL (production)

## Requirements

- Python >= 3.13
- uv (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd context_mcp
```

2. Install dependencies using uv:
```bash
uv sync
```

## Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

### Required Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CON_MCP_DB_TYPE` | Database type: `sqlite` or `postgres` | `sqlite` | `sqlite` |
| `CON_MCP_TRANSPORT` | MCP transport method: `stdio` or `http` | `stdio` | `stdio` |

### SQLite Configuration (when `CON_MCP_DB_TYPE=sqlite`)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `CON_MCP_SQLITE_PATH` | Path to SQLite database file | `./data.db` | `./data.db` |

### PostgreSQL Configuration (when `CON_MCP_DB_TYPE=postgres`)

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `DB_HOST` | PostgreSQL host | Yes | `localhost` |
| `DB_USER` | PostgreSQL username | Yes | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | Yes | `your_password` |
| `DB_NAME` | PostgreSQL database name | Yes | `context_mcp` |
| `DB_PORT` | PostgreSQL port | Yes | `5432` |

### Example Configuration

**For SQLite (Development):**
```env
CON_MCP_DB_TYPE=sqlite
CON_MCP_SQLITE_PATH=./data.db
CON_MCP_TRANSPORT=stdio
```

**For PostgreSQL (Production):**
```env
CON_MCP_DB_TYPE=postgres
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_NAME=context_mcp
DB_PORT=5432
CON_MCP_TRANSPORT=stdio
```

### Configuration Module (`config_env.py`)

The project includes a thread-safe singleton module for environment variable management. This module automatically finds and loads the `.env` file from the project root.

#### Features

- **Thread-safe singleton**: Ensures only one instance exists across the application
- **Auto-discovery**: Automatically searches for `.env` file starting from the module's directory and traversing up to parent directories
- **One-time loading**: Environment variables are loaded only once at initialization
- **Snapshot isolation**: Captures a copy of environment variables at initialization time

#### Usage

```python
# Import the pre-instantiated singleton
from config_env import env_vars

# Get environment variables with optional default values
db_type = env_vars.get("CON_MCP_DB_TYPE", "sqlite")
db_host = env_vars.get("DB_HOST")  # Returns None if not set
transport = env_vars.get("CON_MCP_TRANSPORT", "stdio")
```

#### Why Use `config_env.py`?

Instead of calling `load_dotenv()` in multiple places:

```python
# Traditional approach (scattered across files)
from dotenv import load_dotenv
import os

load_dotenv()
db_type = os.getenv("CON_MCP_DB_TYPE")
```

Use the centralized configuration module:

```python
# Recommended approach (single source of truth)
from config_env import env_vars

db_type = env_vars.get("CON_MCP_DB_TYPE")
```

**Benefits:**
- Single point of environment loading
- Consistent access pattern across the codebase
- Thread-safe for multi-threaded applications
- Automatic `.env` file discovery

## Database Setup

### Database Connection

The application uses SQLAlchemy with async support for database operations:
- **SQLite**: Uses `sqlite+aiosqlite` driver for async operations
- **PostgreSQL**: Uses `postgresql+asyncpg` driver for async operations

### Running Migrations

The project uses Alembic for database migrations. Migrations must be run before starting the server.

#### Using SQLite (Default)

```bash
uv run alembic upgrade head
```

#### Using PostgreSQL

```bash
CON_MCP_DB_TYPE=postgres uv run alembic upgrade head
```

Or set `CON_MCP_DB_TYPE=postgres` in your `.env` file and run:
```bash
uv run alembic upgrade head
```

### Migration Commands

Create a new migration:
```bash
uv run alembic revision --autogenerate -m "description of changes"
```

Upgrade to latest migration:
```bash
uv run alembic upgrade head
```

Downgrade one migration:
```bash
uv run alembic downgrade -1
```

View migration history:
```bash
uv run alembic history
```

View current migration version:
```bash
uv run alembic current
```

## Running the Server

Start the MCP server:

```bash
uv run python main.py
```

Or with specific database:

```bash
# SQLite
CON_MCP_DB_TYPE=sqlite uv run python main.py

# PostgreSQL
CON_MCP_DB_TYPE=postgres uv run python main.py
```

## Available MCP Tools

The server provides the following tools for issue management:

### Issue Creation & Management

- **`con_mcp_create_issue`**: Create tasks, subtasks, or epics with priorities (P0-P4), status tracking, labels, dependencies, time estimates, and assignees
- **`con_mcp_create_child_issue`**: Create a child issue under a parent for hierarchical task organization (auto-creates parent-child dependency)
- **`con_mcp_create_epic_with_children`**: Create an epic with multiple child tasks in one operation, automatically establishing parent-child relationships
- **`con_mcp_update_issue_fields`**: Update one or more fields of an existing issue (status, priority, title, assignee, description, notes, etc.)
- **`con_mcp_claim_issue`**: Claim an issue (assign to yourself and set to in_progress)
- **`con_mcp_close_issue`**: Close an issue with a reason

### Labels & Tags

- **`con_mcp_add_labels`**: Add labels/tags to an existing issue
- **`con_mcp_remove_labels`**: Remove specific labels from an issue
- **`con_mcp_set_labels`**: Replace all labels on an issue with a new set

### Dependencies & Relationships

- **`con_mcp_add_dependency`**: Add dependency relationships between issues (blocks, parent-child, related, duplicates, supersedes)
- **`con_mcp_remove_dependency`**: Remove a dependency relationship between issues

### Comments & Events

- **`con_mcp_add_comment`**: Add a comment/note to an issue for discussions and updates
- **`con_mcp_add_event`**: Add a custom event log entry to track actions and changes

### Query Tools

- **`con_mcp_get_issue_details`**: Get comprehensive details about an issue including all fields, labels, comments, dependencies, dependents, and parent

## Development

### Adding New Tools

1. Create a new tool file in the `tools/` directory
2. Import `mcp` from `mcp_engine.py`
3. Use the `@mcp.tool()` decorator to define tools
4. Export the tool in `tools/__init__.py`

### Database Models

SQLAlchemy models are located in `database/models/`. To add new models:

1. Create the model in `database/models/`
2. Import it in `database/models/__init__.py`
3. Create a migration: `uv run alembic revision --autogenerate -m "add new model"`
4. Review and apply the migration: `uv run alembic upgrade head`

### Session Management

The project uses a context-based session management system:

- **`auto_session()`**: Automatically manages sessions (use in service functions)
- **`session_scope()`**: Manual session control with transaction management
- **`get_session()`**: Get current session from context

### Code Quality with Ruff

Lint the project:
```bash
uv run ruff check
```

Format the project:
```bash
uv run ruff format
```

### Branch Naming Convention

When creating a new branch, follow this naming format:

**Format:** `{initials}-{project-name}-{type}-{description}`

**Example:**
```bash
git checkout -b ha-con_mcp-feature-init-fastmcp-server
```

**Components:**
- **initials**: Your name initials (e.g., `ha` for Haba Andrei)
- **project-name**: The project name (e.g., `con_mcp`)
- **type**: The type of change:
  - `feature` - New functionality
  - `bugfix` - Bug fixes
  - `hotfix` - Urgent production fixes
  - `refactor` - Code refactoring
  - `docs` - Documentation updates
- **description**: Brief summary of what you're building (e.g., `new-ui`, `comprehensive-readme`)

**Examples:**
```bash
# Feature branch
git checkout -b ha-con_mcp-feature-add-user-auth

# Bug fix branch
git checkout -b ha-con_mcp-bugfix-fix-dependency-loop

# Documentation branch
git checkout -b ha-con_mcp-docs-api-documentation
```

## Database Schema

The database includes the following main tables:

- **issues**: Core issue/task data with status, priority, assignee, time tracking
- **comments**: Comments and notes on issues
- **events**: Custom event log entries
- **labels**: Tags and labels for categorization
- **dependencies**: Relationships between issues (blocks, parent-child, etc.)
- **child_counters**: Tracking child issue numbering for epics