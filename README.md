# noMCP

**Skip MCP. Enjoy CLI.**

Use MCP server tools directly from your terminal. Perfect for scripting, automation, and agentic workflows.

## Install

```bash
pip install nomcp
```

## Quick Start

```bash
# Configure your MCP servers in .nomcp/config.json
nomcp clt init playwright     # Initialize a server
nomcp playwright <tool>       # Run tools directly
```

## Persistent Mode

By default, each tool call spawns a new MCP server process. For faster repeated calls, use persistent mode:

```bash
nomcp clt start playwright    # Start server persistently
nomcp playwright <tool>       # Fast: reuses running server
nomcp playwright <tool>       # Fast: still reusing
nomcp clt stop playwright     # Stop when done
```

## Config

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

## Why noMCP?

MCP servers offer powerful, structured tools. But the MCP protocol loads large tool schemas and verbose data into AI context—expensive in tokens, slow in practice.

CLI is leaner. It avoids loading tool schemas and verbose outputs into model context.

noMCP gives you direct CLI access to MCP server tools. Same tools, no protocol overhead.

See [Playwright CLI vs MCP](https://github.com/microsoft/playwright-mcp#cli-mode-vs-mcp-mode) for a similar motivation.

## Why this tool?

Not every MCP server has an official CLI. Rather than waiting, noMCP lets you use existing MCP servers as CLIs right now.

## Architecture

### On-Demand Mode (Default)

Each tool call spawns a new MCP server, executes the tool, and exits:

```mermaid
sequenceDiagram
    participant CLI as nomcp CLI
    participant TR as ToolRunner
    participant MCP as MCP Server

    CLI->>TR: call(tool, args)
    TR->>MCP: spawn process
    TR->>MCP: initialize session
    TR->>MCP: call_tool()
    MCP-->>TR: result
    TR->>MCP: exit
    TR-->>CLI: result
```

### Persistent Mode

A daemon process keeps the MCP server running. Tool calls connect via Unix socket:

```mermaid
sequenceDiagram
    participant CLI as nomcp CLI
    participant SM as ServerManager
    participant D as Daemon
    participant MCP as MCP Server

    Note over CLI,MCP: nomcp clt start playwright
    CLI->>SM: start("playwright")
    SM->>D: spawn daemon process
    D->>MCP: spawn & initialize
    D->>D: listen on socket

    Note over CLI,MCP: nomcp playwright browser_navigate
    CLI->>D: connect to socket
    CLI->>D: {"method": "call_tool", ...}
    D->>MCP: call_tool()
    MCP-->>D: result
    D-->>CLI: {"content": [...]}

    Note over CLI,MCP: nomcp clt stop playwright
    CLI->>D: {"method": "shutdown"}
    D->>MCP: close session
    D->>D: cleanup & exit
```

### Component Overview

```mermaid
flowchart TB
    subgraph CLI["CLI Layer"]
        cmd["nomcp commands"]
    end

    subgraph Services["Service Layer"]
        sm["ServerManager"]
        tr["ToolRunner"]
        pm["ProcessManager"]
    end

    subgraph Runtime["Runtime"]
        daemon["Daemon Process"]
        socket["Unix Socket"]
        mcp["MCP Server"]
    end

    subgraph Storage["Storage (.nomcp/)"]
        config["config.json"]
        procs["processes.json"]
        sockets["sockets/*.sock"]
        cache["servers/*.json"]
    end

    cmd --> sm
    cmd --> tr
    sm --> pm
    sm --> daemon
    tr --> socket
    daemon --> socket
    daemon --> mcp
    pm --> procs
    sm --> config
    tr --> cache
    daemon --> sockets
```

### File Structure

```
.nomcp/
├── config.json          # Server configurations
├── processes.json       # Running process registry
├── servers/
│   └── playwright.json  # Cached tools per server
└── sockets/
    └── playwright.sock  # Unix socket (persistent mode)
```

## Status

Under active development.

## License

MIT
