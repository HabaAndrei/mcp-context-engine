# Integrating Context MCP with LangChain + LangGraph

This guide explains how to integrate the Context MCP server with LangChain and LangGraph to create AI agents with persistent memory and task management capabilities.

## Overview

By integrating this Context MCP server with LangChain and LangGraph, you enable AI agents to:

- **Maintain persistent context** across conversations using the task management system
- **Track complex multi-step workflows** by creating and updating issues, epics, and tasks
- **Resume work seamlessly** after interruptions by querying issue state
- **Manage dependencies** between different tasks in a workflow
- **Store conversation state** in PostgreSQL using LangGraph's checkpointing feature

## Prerequisites

### Required Dependencies

Install the following packages using `uv`:

```bash
# Core LangChain and LangGraph packages
uv add langchain langchain-mcp-adapters langgraph

# Database support for checkpointing
uv add langgraph-checkpoint-postgres asyncpg psycopg2-binary

# Environment management
uv add python-dotenv

# LLM provider (example uses OpenAI)
uv add langchain-openai
```

Or install all at once:

```bash
uv add langchain langchain-mcp-adapters langgraph langgraph-checkpoint-postgres asyncpg psycopg2-binary python-dotenv langchain-openai
```

### Environment Setup

Create a `.env` file with the following variables:

```env
# OpenAI API Key (or your preferred LLM provider)
OPENAI_API_KEY=your_openai_api_key_here

# PostgreSQL Configuration (for LangGraph checkpointing)
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=your_database
DB_PORT=5432

# Context MCP Server Configuration
CON_MCP_TRANSPORT=stdio
CON_MCP_DB_TYPE=sqlite  # or postgres
CON_MCP_SQLITE_PATH=./data.db
```

## Integration Architecture

```
┌─────────────────┐
│  LangChain      │
│  Agent          │
│  (GPT-5, etc.)  │
└────────┬────────┘
         │
         │ Uses tools from
         ▼
┌─────────────────┐       ┌──────────────────┐
│  MultiServer    │◄─────►│  Context MCP     │
│  MCP Client     │ stdio │  Server          │
└─────────────────┘       └────────┬─────────┘
         │                          │
         │                          │ Stores tasks
         ▼                          ▼
┌─────────────────┐       ┌──────────────────┐
│  LangGraph      │       │  SQLite/         │
│  Checkpointer   │       │  PostgreSQL      │
│  (PostgreSQL)   │       │  (Issues DB)     │
└─────────────────┘       └──────────────────┘
```

## Step-by-Step Integration

### 1. Import Required Modules

```python
import asyncio

# Use the centralized environment configuration module
from config_env import env_vars

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
```

> **Note:** The `config_env` module provides a thread-safe singleton that automatically loads environment variables from your `.env` file. See the main README for more details on this module.

### 2. Configure Database Connection

Set up the PostgreSQL connection for LangGraph's checkpointing feature:

```python
# Load database credentials using the env_vars singleton
DB_HOST = env_vars.get("DB_HOST")
DB_USER = env_vars.get("DB_USER")
DB_PASSWORD = env_vars.get("DB_PASSWORD")
DB_NAME = env_vars.get("DB_NAME")
DB_PORT = env_vars.get("DB_PORT")

# Create synchronous connection string for PostgreSQL
SYNC_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Get OpenAI API key
api_key = env_vars.get("OPENAI_API_KEY")
```

### 3. Initialize the MCP Client

Create a `MultiServerMCPClient` that connects to your Context MCP server:

```python
client = MultiServerMCPClient(
    {
        "context_engine": {
            "transport": "stdio",  # Local subprocess communication
            "command": "python",
            # Absolute path to your MCP server
            "args": ["/absolute/path/to/context_mcp/main.py"],
        },
    }
)
```

**Key Configuration Options:**

- **`transport`**: Communication method (`stdio` for local subprocess, `http` for remote server)
- **`command`**: Executable to run (e.g., `python`, `uv run python`, `node`)
- **`args`**: List containing the path to your MCP server script

**Example with `uv`:**
```python
"command": "uv",
"args": ["run", "python", "/path/to/main.py"],
```

### 4. Get MCP Tools

Retrieve all available tools from the Context MCP server:

```python
tools = await client.get_tools()
```

This returns a list of LangChain-compatible tools that the agent can use, including:
- `con_mcp_create_issue`
- `con_mcp_create_epic_with_children`
- `con_mcp_get_issue_details`
- `con_mcp_update_issue_fields`
- And all other tools defined in the Context MCP server

### 5. Set Up LangGraph Checkpointing

Initialize the PostgreSQL checkpointer for persistent conversation state:

```python
async with AsyncPostgresSaver.from_conn_string(SYNC_DATABASE_URL) as checkpointer:
    # Auto-create required tables in PostgreSQL
    await checkpointer.setup()

    # Continue with agent creation...
```

**What does checkpointing do?**
- Stores conversation history in PostgreSQL
- Allows agents to resume conversations from any point
- Enables branching conversations with different thread IDs
- Provides automatic state persistence across restarts

### 6. Create the LangChain Agent

Create an agent with the MCP tools and checkpointing:

```python
agent = create_agent(
    "gpt-5",  # Or "gpt-4", "claude-3-opus", etc.
    tools,
    checkpointer=checkpointer,
)
```

### 7. Configure Thread and Execute

Set up a conversation thread and invoke the agent:

```python
# Configure the thread ID for conversation persistence
config = {
    "configurable": {
        "thread_id": "3",  # Unique ID for this conversation
    },
}

# Invoke the agent with a message
response = await agent.ainvoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Create an epic with multiple steps about how I can create a sign in page with MFA, nice frontend, tests, and validations"
            }
        ]
    },
    config
)

# Extract the response
messages = response.get("messages")
print(f"Total messages: {len(messages)}")
print(f"Assistant response: {messages[-1].content}")
```

## Complete Example

Here's the full integration code:

```python
import asyncio

# Use the centralized environment configuration module
from config_env import env_vars

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Database configuration using env_vars singleton
DB_HOST = env_vars.get("DB_HOST")
DB_USER = env_vars.get("DB_USER")
DB_PASSWORD = env_vars.get("DB_PASSWORD")
DB_NAME = env_vars.get("DB_NAME")
DB_PORT = env_vars.get("DB_PORT")

SYNC_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
api_key = env_vars.get("OPENAI_API_KEY")


async def main():
    # Initialize checkpointer
    async with AsyncPostgresSaver.from_conn_string(SYNC_DATABASE_URL) as checkpointer:
        await checkpointer.setup()

        # Initialize MCP client
        client = MultiServerMCPClient(
            {
                "context_engine": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["/absolute/path/to/context_mcp/main.py"],
                },
            }
        )

        # Get tools from MCP server
        tools = await client.get_tools()

        # Create agent with tools and checkpointing
        agent = create_agent(
            "gpt-5",
            tools,
            checkpointer=checkpointer,
        )

        # Configure conversation thread
        config = {
            "configurable": {
                "thread_id": "my_conversation_1",
            },
        }

        # Invoke agent
        response = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Create an epic for building a user authentication system with child tasks"
                    }
                ]
            },
            config
        )

        # Print response
        messages = response.get("messages")
        print(messages[-1].content)


# Run the async function
asyncio.run(main())
```

## Advanced Usage

### Multiple MCP Servers

You can connect to multiple MCP servers simultaneously:

```python
client = MultiServerMCPClient(
    {
        "context_engine": {
            "transport": "stdio",
            "command": "python",
            "args": ["/path/to/context_mcp/main.py"],
        },
        "file_system": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
        },
    }
)
```

### Conversation Threading

Use different thread IDs to maintain separate conversation contexts:

```python
# Conversation 1
config_1 = {"configurable": {"thread_id": "project_auth"}}
response_1 = await agent.ainvoke({"messages": [...]}, config_1)

# Conversation 2 (completely separate context)
config_2 = {"configurable": {"thread_id": "project_api"}}
response_2 = await agent.ainvoke({"messages": [...]}, config_2)
```

### Resuming Conversations

Resume a previous conversation by using the same thread ID:

```python
# Initial conversation
config = {"configurable": {"thread_id": "auth_flow"}}
await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Create tasks for auth system"}]},
    config
)

# Later... resume the same conversation
await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Update task 1.1 to completed"}]},
    config  # Same thread_id
)
```

### Custom Agent Configuration

Customize the agent behavior:

```python
from langchain.agents import AgentExecutor

agent = create_agent(
    model="gpt-4",
    tools=tools,
    checkpointer=checkpointer,
    system_message="You are a project management assistant. Always break down complex tasks into smaller, manageable issues.",
    agent_type="openai-tools",  # or "structured-chat-zero-shot-react-description"
)
```

## Use Cases

### 1. Project Planning and Tracking

```python
response = await agent.ainvoke({
    "messages": [{
        "role": "user",
        "content": "Create an epic for building a REST API with tasks for endpoints, authentication, testing, and documentation"
    }]
}, config)
```

The agent will:
1. Use `con_mcp_create_epic_with_children` to create the epic
2. Create child tasks for each component
3. Track all tasks in the Context MCP database
4. Return the epic and task IDs for future reference

### 2. Multi-Step Workflow Execution

```python
# Step 1: Create tasks
await agent.ainvoke({
    "messages": [{
        "role": "user",
        "content": "Create tasks for: 1) Design database schema, 2) Implement API, 3) Write tests"
    }]
}, config)

# Step 2: Update progress (in a later conversation)
await agent.ainvoke({
    "messages": [{
        "role": "user",
        "content": "Mark task 1 as complete and add a comment about the schema decisions"
    }]
}, config)

# Step 3: Query status
await agent.ainvoke({
    "messages": [{
        "role": "user",
        "content": "What tasks are still pending?"
    }]
}, config)
```

### 3. Dependency Management

```python
response = await agent.ainvoke({
    "messages": [{
        "role": "user",
        "content": "Create a task for frontend implementation that depends on the API task being completed first"
    }]
}, config)
```

The agent will use `con_mcp_add_dependency` to create a "blocks" relationship between tasks.

## Benefits of This Integration

### For AI Agents

1. **Persistent Memory**: Tasks and their state persist across conversations
2. **Structured Context**: Hierarchical organization (epics → tasks → subtasks)
3. **Dependency Tracking**: Understand what needs to be done before other tasks
4. **Progress Monitoring**: Query and track what's complete, in progress, or blocked

### For Developers

1. **Resume Work**: Pick up exactly where you left off, even days later
2. **Clear Progress**: See what the AI has accomplished and what remains
3. **Audit Trail**: Comments and events provide a history of decisions
4. **Collaboration**: Multiple agents or users can work on the same task list

### For Complex Workflows

1. **Break Down Complexity**: Large projects become manageable task hierarchies
2. **Track Blockers**: Know exactly what's preventing progress
3. **Time Estimation**: Track estimated vs actual time for tasks
4. **Label Organization**: Categorize tasks by type, priority, or domain

## Troubleshooting

### MCP Server Connection Issues

**Problem**: Agent can't connect to MCP server

**Solution**: Ensure the path to `main.py` is absolute:
```python
import os
from pathlib import Path

# Get absolute path
mcp_path = str(Path(__file__).parent / "main.py")

client = MultiServerMCPClient({
    "context_engine": {
        "transport": "stdio",
        "command": "python",
        "args": [mcp_path],
    },
})
```

### Database Connection Errors

**Problem**: PostgreSQL connection fails

**Solution**: Verify your connection string and credentials:
```python
# Test connection
import asyncpg

async def test_connection():
    conn = await asyncpg.connect(SYNC_DATABASE_URL)
    await conn.close()
    print("Connection successful!")

asyncio.run(test_connection())
```

### Checkpointer Table Issues

**Problem**: Missing checkpointer tables

**Solution**: Always call `setup()`:
```python
async with AsyncPostgresSaver.from_conn_string(SYNC_DATABASE_URL) as checkpointer:
    await checkpointer.setup()  # This creates required tables
```

### Tool Execution Failures

**Problem**: Agent tries to use tools but fails

**Solution**: Check that the Context MCP server is running migrations:
```bash
cd /path/to/context_mcp
uv run alembic upgrade head
```

### Thread State Confusion

**Problem**: Agent doesn't remember previous conversation

**Solution**: Ensure you're using the same thread_id:
```python
# Store thread ID
THREAD_ID = "my_persistent_thread"

config = {"configurable": {"thread_id": THREAD_ID}}

# Use same config for all related conversations
response1 = await agent.ainvoke({"messages": [...]}, config)
response2 = await agent.ainvoke({"messages": [...]}, config)  # Same thread
```

## Best Practices

1. **Use Descriptive Thread IDs**: Name threads after projects or features (e.g., `"auth_system"`, `"api_v2"`)

2. **Let the Agent Manage Tasks**: Instead of manually creating issues, ask the agent to break down work:
   ```python
   "Create an epic with tasks for building feature X"
   ```

3. **Query Before Acting**: Let the agent check task state before working:
   ```python
   "What tasks are pending? Let's work on the highest priority one."
   ```

4. **Use Labels Consistently**: Ask the agent to label tasks by category:
   ```python
   "Label this task as 'backend' and 'authentication'"
   ```

5. **Add Context with Comments**: Record decisions and blockers:
   ```python
   "Add a comment to task 1.2 explaining why we chose JWT over sessions"
   ```

6. **Close Loops**: Mark tasks complete when done:
   ```python
   "Mark task 1.1 as complete and create the next task"
   ```

## Next Steps

- Explore other MCP tools available in the Context MCP server
- Experiment with different LLM models (GPT-4, Claude, etc.)
- Build custom workflows combining multiple MCP servers
- Integrate with CI/CD pipelines for automated task updates
- Create dashboards to visualize task progress from the database
