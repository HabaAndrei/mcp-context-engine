# Context MCP

An [MCP](https://modelcontextprotocol.io) server that gives a coding agent an
issue tracker it can rely on as external memory. Issues, epics, dependencies,
labels, comments and an audit trail live in SQLite or PostgreSQL, so what the
agent knew in one session is still there in the next.

Built with [FastMCP](https://github.com/jlowin/fastmcp) and SQLAlchemy.

---

## The problem it solves

An agent working a long task holds its plan in the conversation. That plan is
the first thing lost to a context window limit, a crashed session, or a
colleague picking the work up on another machine. What survives is prose — a
checklist in a markdown file that nothing validates and everything drifts from.

This server moves the plan out of the transcript and into a database with
structure the agent can query:

```
Agent: "What should I work on?"
  -> con_mcp_get_ready_work
  -> [#12 "Add token refresh" (P1), #15 "Write auth tests" (P2)]

Agent: "Why can't I start #14?"
  -> con_mcp_get_blocked_issues
  -> #14 is blocked by #12, which is still open
```

The distinction that makes this more than a to-do list is **dependency
awareness**. The server knows which work is genuinely startable, so the agent
does not have to reload the whole board and reason it out each time.

```mermaid
sequenceDiagram
    actor User
    participant AI as Coding agent
    participant MCP as Context MCP
    participant DB as SQLite / PostgreSQL

    User->>AI: "Build the authentication system"
    AI->>MCP: con_mcp_create_epic_with_children(...)
    MCP->>DB: one transaction: epic + children + edges
    AI->>MCP: con_mcp_claim_issue(#35;12)
    AI->>MCP: con_mcp_close_issue(#35;12, "Completed")
    Note over User,AI: session ends, context is gone
    User->>AI: "Where were we?" (new session)
    AI->>MCP: con_mcp_get_ready_work()
    MCP->>DB: open issues with no unfinished blockers
    MCP-->>AI: #35;13 and #35;15 are startable; #35;14 waits on #35;13
    AI-->>User: exact state, nothing forgotten
```

---

## Install

Requires **Python 3.13+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/HabaAndrei/mcp-context-engine.git
cd mcp-context-engine
uv sync
cp .env.example .env
uv run alembic upgrade head    # create the schema
```

Run it:

```bash
uv run python main.py
```

### Connecting a client

For a stdio client such as Claude Desktop:

```json
{
  "mcpServers": {
    "context": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/mcp-context-engine", "run", "python", "main.py"],
      "env": { "CON_MCP_DB_TYPE": "sqlite", "CON_MCP_SQLITE_PATH": "./data.db" }
    }
  }
}
```

For LangChain and LangGraph, including checkpointing so both the conversation
and the task state survive a restart, see
[LANGCHAIN_INTEGRATION.md](LANGCHAIN_INTEGRATION.md).

---

## Configuration

Read from the environment, or from a `.env` file discovered by walking up from
the project directory.

| Variable | Purpose | Default |
|---|---|---|
| `CON_MCP_DB_TYPE` | `sqlite` or `postgres` | `sqlite` |
| `CON_MCP_TRANSPORT` | `stdio` or `http` | `stdio` |
| `CON_MCP_SQLITE_PATH` | Database file, when using SQLite | `./data.db` |
| `DB_HOST` `DB_PORT` `DB_USER` `DB_PASSWORD` `DB_NAME` | Required when using PostgreSQL | — |

Values come from the process environment first, and from `.env` only where the
environment is silent. That ordering matters: MCP clients pass configuration
through an `env` block in their config file, and a leftover `.env` in the
checkout must not quietly override it.

An unrecognised `CON_MCP_DB_TYPE`, or a PostgreSQL setup missing a variable,
raises `ConfigurationError` naming what is wrong. The engine is built on first
use, so a database that is merely unreachable surfaces as a tool error rather
than stopping the server from starting at all.

---

## Concepts

**Issues** are the unit of work. Epics, tasks and subtasks are all issues,
distinguished by `issue_type`.

**Priority** runs 0 (most urgent) to 4 (least). Pinned issues sort above
everything and need `force=True` to close.

**Status** is one of `open`, `in_progress`, `blocked`, `deferred`, `closed`.

**Dependencies** are directed edges. Only `blocks` affects what is startable:

| Type | Meaning | Gates execution? |
|---|---|---|
| `blocks` | The source cannot start until the target closes | **Yes** |
| `parent-child` | The source is a child of the target | No |
| `related` / `duplicates` / `supersedes` | Annotation | No |

Hierarchy is an edge rather than a column, so re-parenting is a one-row change
and containment is queried the same way as blocking. Grouping and sequencing
stay separate: a task inside an unfinished epic is still startable, which is
usually what you want, since an epic is finished only when its children are.

**Ready work** — open, not an epic, and every `blocks` dependency closed. This
is the query an agent should lead with.

`blocks` and `parent-child` edges are kept acyclic. A blocking cycle would make
every issue in it permanently unstartable, so edges that would close one are
refused when added.

---

## Tools

### Planning and lifecycle

| Tool | Purpose |
|---|---|
| `con_mcp_create_issue` | Create a task, subtask or epic |
| `con_mcp_create_child_issue` | Create an issue nested under a parent |
| `con_mcp_create_epic_with_children` | Create an epic and its children atomically |
| `con_mcp_update_issue_fields` | Partial update; each change is audited |
| `con_mcp_claim_issue` | Take ownership and mark in progress |
| `con_mcp_unassign_issue` | Release back to the pool |
| `con_mcp_close_issue` | Close with a reason |
| `con_mcp_reopen_issue` | Return a closed issue to an active status |

### Querying

| Tool | Purpose |
|---|---|
| `con_mcp_get_ready_work` | **What can be started right now**, best first |
| `con_mcp_get_blocked_issues` | What is stuck, and what is blocking it |
| `con_mcp_get_issue_details` | One issue with labels, comments, edges, parent |
| `con_mcp_list_issues` | Filter by status, type, assignee, priority, labels, text |
| `con_mcp_get_issue_tree` | An epic and its descendants |
| `con_mcp_get_issue_stats` | Board-wide counts including ready and blocked |
| `con_mcp_find_dependency_cycles` | Diagnose cycles in existing data |

### Relationships and notes

| Tool | Purpose |
|---|---|
| `con_mcp_add_dependency` / `con_mcp_remove_dependency` | Manage edges |
| `con_mcp_add_labels` / `con_mcp_remove_labels` / `con_mcp_set_labels` | Manage labels |
| `con_mcp_add_comment` | Record a decision and why it was made |
| `con_mcp_add_event` | Record a custom audit entry |

Tools return structured JSON. On failure they return a readable message rather
than raising, because the caller is a language model that can correct itself
and retry — an exception would just end its turn.

**Deletion is deliberately not exposed.** It is unrecoverable and takes the
comments and audit trail with it. Closing conveys the same meaning and keeps
the history. `database.services.delete_issue` exists for operators who need it.

---

## Architecture

```
main.py            entry point; picks transport, starts the server
mcp_engine.py      the shared FastMCP instance and its instructions
config_env.py      loads .env once into a snapshot

tools/             MCP surface: argument docs, error-to-message conversion
database/
  settings.py      env vars -> validated SQLAlchemy URL
  db_client.py     lazy engine, ambient-session context manager
  domain.py        statuses, edge types, priorities, validators
  serializers.py   ORM rows -> JSON-safe dicts
  models/          one table per module
  services/        issue_service.py (writes) / issue_query_service.py (reads)
```

Four ideas carry most of the weight:

**Layering.** Tools handle presentation and never touch the ORM. Services own
the rules. Models own the schema. Business logic is testable without a server.

**Ambient sessions.** Services acquire a session through `auto_session()`,
which joins an open transaction if there is one and otherwise opens a
self-committing one. The same function therefore works standalone and as part
of a larger unit of work — which is how `create_epic_with_children` gets to be
atomic without any function knowing it is being composed.

```python
from database.db_client import session_scope
from database.services import add_comment, create_issue

async with session_scope():
    issue = await create_issue(title="Ship the parser", priority=1)
    await add_comment(issue["id"], author="ana", text="Agreed in review")
# both committed together, or neither
```

**Validation at the boundary.** Statuses and edge types are strings in the
database, so a typo like `"in-progress"` would otherwise become a row no filter
ever returns. `domain.py` rejects it at the service boundary instead.

**Explicit serialization.** Every returned dict is built field by field and
timestamps are ISO-8601 strings, so results survive `json.dumps` intact.

---

## Development

```bash
uv run pytest                      # 135 tests
uv run pytest -m "not integration" # skip the ones that spawn a server
uv run ruff check
uv run ruff format
```

Unit tests run against a temporary SQLite file created from the model
metadata — no server, no migrations, no cleanup. A file rather than
`:memory:`, because an in-memory SQLite database belongs to one connection and
appears to vanish the moment the pool opens a second.

Coverage is behavioural: creation and validation, the claim/close/reopen
lifecycle, dependency semantics and cycle prevention, ready-work and blocked
calculations, filtering and paging, transaction rollback, cascade deletion,
configuration precedence, and the tool layer's guarantee that it returns
messages instead of raising.

The `integration` tests go further and launch `main.py` as a real subprocess,
speaking MCP over stdio: handshake and tool discovery, a full plan → claim →
close → re-discover workflow, errors arriving as messages without dropping the
session, and state surviving a complete server restart.

### Changing the schema

```bash
uv run alembic revision --autogenerate -m "what changed"
uv run alembic upgrade head
uv run alembic check        # confirm models and migrations agree
```

---

## Limitations

- **Single writer.** No optimistic locking. `claim_issue` prevents two agents
  taking the same task, but simultaneous edits to the same fields are
  last-write-wins. SQLite in particular serialises writers.
- **No authentication.** Anyone who can reach the server has full access.
  Do not expose the HTTP transport to an untrusted network.
- **No full-text search.** `search` is a `LIKE` scan; fine for thousands of
  issues, not for millions.
- **Result caps.** Queries return at most 500 rows. Large boards need paging.
- **`update_issue_fields` cannot clear a field**, since omission means "leave
  alone". Use `con_mcp_unassign_issue` to remove an assignee.
- **Cycle prevention is per-edge.** Data written by an older version or edited
  by hand can still contain cycles; `con_mcp_find_dependency_cycles` finds them.
- **Time tracking is an estimate field only.** Nothing accumulates actual time.

---

## License and attribution

Released under the [MIT License](LICENSE).

The idea this project builds on — giving a coding agent a dependency-aware
issue graph as external memory — comes from
**[Beads](https://github.com/steveyegge/beads)** by Steve Yegge and the Beads
Contributors, also MIT licensed. Concepts adopted from it include treating
epics, tasks and subtasks as one issue kind, expressing hierarchy as a
parent-child edge, the vocabulary of dependency types, and "ready work" as
open issues with no unfinished blockers.

This is an independent implementation rather than a port: Beads is Go backed by
Dolt and driven from a CLI, while this is Python on SQLAlchemy exposed as MCP
tools. The schema, services, queries, validation and tests were written for
this codebase, and no Beads source code was copied.

See [NOTICE](NOTICE) for full attribution and third-party dependency licenses.
