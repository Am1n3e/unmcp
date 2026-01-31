# noMCP - CLI Interface for MCP Servers

## Overview

noMCP is a CLI tool that creates simple command-line interfaces to MCP (Model Context Protocol) servers. It allows users to interact with MCP server tools directly from the terminal without needing an AI client.

**CLI command:** `nomcp`

## Configuration

nomcp reads server definitions from `.nomcp/config.json`:

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

Config search paths (in order):
1. `.nomcp/config.json` (project local)
2. `~/.nomcp/config.json` (user global)

## Commands

### Server Management (`nomcp clt`)

```bash
nomcp clt init <server>     # Initialize server and discover tools
nomcp clt stop <server>     # Stop a running server
nomcp clt status [server]   # Show server status
nomcp clt list              # List configured servers
```

### Tool Execution

```bash
nomcp <server> <tool> [args]   # Execute a tool on a server
```

Example:
```bash
nomcp playwright browser_navigate --url="https://example.com"
```

## Internal Process Manager

A lightweight process manager built into nomcp:

- Stores process metadata in `.nomcp/processes.json`
- Tracks: PID, server name, start time, port (if applicable)
- Operations: start, stop, status check (PID alive)

## File Structure

```
.nomcp/
├── config.json         # Server configuration
├── processes.json      # Running process registry
└── servers/
    ├── playwright.json # Cached tool definitions for playwright server
    └── <server>.json   # Cached tool definitions for other servers
```

## Dependencies

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) - For communicating with MCP servers
- Python standard library for process management (subprocess, os, signal)

## References

- [Playwright MCP Server](https://github.com/microsoft/playwright-mcp) - Example MCP server
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) - Client SDK
