# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run the CLI
uv run unmcp --help

# Linting & formatting
uv run ruff check .          # lint
uv run ruff check --fix .    # lint with auto-fix
uv run ruff format .         # format

# Type checking
uv run ty check
```

## Architecture Overview

unmcp is a CLI that provides direct command-line access to MCP (Model Context Protocol) servers, bypassing the protocol overhead for simpler workflows.

### Two Execution Modes

**On-Demand Mode (default):** Each tool call spawns a new MCP server process, executes the tool, and exits. Simple but slower for repeated calls.

**Persistent Mode:** A daemon process keeps the MCP server running, communicating via Unix socket. Tool calls connect to the daemon rather than spawning new processes.

### Core Components

- **cli.py** - Click-based CLI with `DynamicServerGroup` that dynamically creates subcommands from cached tool schemas. Server tools appear as `unmcp <server> <tool>`.

- **services/server_manager.py** - `ServerManager` handles server lifecycle: init (discover tools), start (spawn daemon), stop, status.

- **services/tool_runner.py** - `ToolRunner` executes tools, automatically routing to socket (persistent) or spawning new process (on-demand).

- **daemon.py** - `DaemonServer` maintains MCP session and exposes it via Unix socket. Accepts JSON-RPC style messages (`call_tool`, `list_tools`, `shutdown`).

- **mcp_client.py** - `MCPClient` wraps the MCP SDK's stdio transport for one-shot server connections.

### Data Flow

1. `unmcp clt init <server>` - connects to MCP server, caches tool schemas to `.unmcp/servers/<server>.json`
2. `unmcp <server> <tool>` - CLI looks up cached schema, builds Click command, invokes `ToolRunner.call()`
3. `ToolRunner` checks for socket at `.unmcp/sockets/<server>.sock`:
   - If exists: sends request via socket to daemon
   - If not: creates `MCPClient`, spawns process, calls tool, exits

### Configuration Files

- `.unmcp/.mcp.json` or `~/.unmcp/.mcp.json` - Server definitions (`mcpServers` object with command/args/env)
- `.unmcp/.settings.json` - Settings (dump_dir, dump_threshold for auto-dumping large outputs)
- `.unmcp/servers/*.json` - Cached tool schemas per server
- `.unmcp/processes.json` - Running daemon registry
- `.unmcp/sockets/*.sock` - Unix sockets for persistent mode
