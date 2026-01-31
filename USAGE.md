# noMCP Usage Guide

noMCP provides a CLI interface to MCP (Model Context Protocol) servers, allowing you to interact with MCP tools directly from the terminal.

## Installation

```bash
uv sync
```

## Configuration

Create `.nomcp/config.json`:

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

## Commands Overview

```
nomcp
├── clt                    # Server management
│   ├── init <server>      # Initialize server and discover tools
│   ├── stop <server>      # Stop a running server
│   ├── status [server]    # Show server status
│   └── list               # List configured servers
│
└── <server> <tool> [opts] # Execute a tool on a server
```

---

## Server Management (`nomcp clt`)

### Initialize a Server

Connects to the MCP server, discovers available tools, and caches them locally.

```bash
$ nomcp clt init playwright
```

**Output:**
```
Initialized server: playwright (v0.0.62)
Discovered 22 tools:
  - browser_close: Close the page
  - browser_resize: Resize the browser window
  - browser_console_messages: Returns all console messages
  - browser_handle_dialog: Handle a dialog
  - browser_evaluate: Evaluate JavaScript expression on page or element
  - browser_file_upload: Upload one or multiple files
  - browser_fill_form: Fill multiple form fields
  - browser_install: Install the browser specified in the config.
  - browser_press_key: Press a key on the keyboard
  - browser_type: Type text into editable element
  - browser_navigate: Navigate to a URL
  - browser_navigate_back: Go back to the previous page in the history
  - browser_network_requests: Returns all network requests since loading the page
  - browser_run_code: Run Playwright code snippet
  - browser_take_screenshot: Take a screenshot of the current page.
  - browser_snapshot: Capture accessibility snapshot of the current page
  - browser_click: Perform click on a web page
  - browser_drag: Perform drag and drop between two elements
  - browser_hover: Hover over element on page
  - browser_select_option: Select an option in a dropdown
  - browser_tabs: List, create, close, or select a browser tab.
  - browser_wait_for: Wait for text to appear or disappear or a specified time to pass
```

### List Configured Servers

```bash
$ nomcp clt list
```

**Output:**
```
playwright: npx @playwright/mcp@latest
```

### Check Server Status

```bash
$ nomcp clt status
```

**Output:**
```
playwright: stopped
```

### Stop a Server

```bash
$ nomcp clt stop playwright
```

**Output:**
```
Stopped server: playwright
```

---

## Tool Execution (`nomcp <server> <tool>`)

After initializing a server, its tools become available as CLI commands.

### List Available Tools

```bash
$ nomcp playwright --help
```

**Output:**
```
Usage: nomcp playwright [OPTIONS] COMMAND [ARGS]...

  Tools for playwright server

Options:
  --help  Show this message and exit.

Commands:
  browser_click             Perform click on a web page
  browser_close             Close the page
  browser_console_messages  Returns all console messages
  browser_drag              Perform drag and drop between two elements
  browser_evaluate          Evaluate JavaScript expression on page or element
  browser_file_upload       Upload one or multiple files
  browser_fill_form         Fill multiple form fields
  browser_handle_dialog     Handle a dialog
  browser_hover             Hover over element on page
  browser_install           Install the browser specified in the config.
  browser_navigate          Navigate to a URL
  browser_navigate_back     Go back to the previous page in the history
  browser_network_requests  Returns all network requests since loading the page
  browser_press_key         Press a key on the keyboard
  browser_resize            Resize the browser window
  browser_run_code          Run Playwright code snippet
  browser_select_option     Select an option in a dropdown
  browser_snapshot          Capture accessibility snapshot of the current page
  browser_tabs              List, create, close, or select a browser tab.
  browser_take_screenshot   Take a screenshot of the current page.
  browser_type              Type text into editable element
  browser_wait_for          Wait for text to appear or disappear
```

### Get Tool Options

```bash
$ nomcp playwright browser_navigate --help
```

**Output:**
```
Usage: nomcp playwright browser_navigate [OPTIONS]

  Navigate to a URL

Options:
  --url TEXT  The URL to navigate to  [required]
  --help      Show this message and exit.
```

### Execute a Tool

#### Navigate to a URL

```bash
$ nomcp playwright browser_navigate --url "https://example.com"
```

**Output:**
```
### Ran Playwright code
```js
await page.goto('https://example.com');
```
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
### Snapshot
```yaml
- generic [ref=e2]:
  - heading "Example Domain" [level=1] [ref=e3]
  - paragraph [ref=e4]: This domain is for use in illustrative examples...
  - paragraph [ref=e5]:
    - link "More information..." [ref=e6] [cursor=pointer]:
      - /url: https://www.iana.org/domains/example
```
```

#### Take a Snapshot

```bash
$ nomcp playwright browser_snapshot
```

**Output:**
```
### Snapshot
```yaml
- generic [ref=e2]:
  - heading "Example Domain" [level=1] [ref=e3]
  - paragraph [ref=e4]: This domain is for use in illustrative examples...
  - link "More information..." [ref=e6]
```
```

#### Click an Element

```bash
$ nomcp playwright browser_click --ref "e6" --element "More information link"
```

---

## File Structure

```
.nomcp/
├── config.json           # Server configuration
└── servers/
    └── playwright.json   # Cached tools (auto-generated by init)
```

## Workflow Example

```bash
# 1. Create config
mkdir -p .nomcp
echo '{"mcpServers":{"playwright":{"command":"npx","args":["@playwright/mcp@latest"]}}}' > .nomcp/config.json

# 2. Initialize server
nomcp clt init playwright

# 3. Use tools
nomcp playwright browser_navigate --url "https://github.com"
nomcp playwright browser_snapshot
nomcp playwright browser_click --ref "e10" --element "Sign in button"
```
