"""MCP client for communicating with MCP servers."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool

from nomcp.config import get_nomcp_dir
from nomcp.models import ToolsCache


def _extract_package_name(args: list[str]) -> str | None:
    """Extract npm package name from command args.

    Handles formats like:
    - @playwright/mcp@latest -> @playwright/mcp
    - @playwright/mcp@0.0.56 -> @playwright/mcp
    - @playwright/mcp -> @playwright/mcp
    """
    for arg in args:
        # Match scoped packages (@org/pkg) or regular packages
        match = re.match(r"^(@?[^@]+)(?:@.*)?$", arg)
        if match:
            pkg = match.group(1)
            # Check if it looks like a package name
            if "/" in pkg or not pkg.startswith("-"):
                return pkg
    return None


def _extract_version_from_args(args: list[str]) -> str | None:
    """Extract version specifier from command args.

    Handles formats like:
    - @playwright/mcp@latest -> latest
    - @playwright/mcp@0.0.56 -> 0.0.56
    - @playwright/mcp -> None
    """
    for arg in args:
        if "@" in arg:
            # Handle scoped packages (@org/pkg@version)
            parts = arg.rsplit("@", 1)
            if (
                len(parts) == 2
                and parts[1]
                and ("/" in parts[0] or not parts[0].startswith("@"))
            ):
                return parts[1]
    return None


def get_package_version(command: str, args: list[str]) -> str | None:
    """Get the version of an npm package.

    Tries npm view first, falls back to parsing args.

    Args:
        command: The command (e.g., "npx")
        args: Command arguments

    Returns:
        Version string or None if not determinable.
    """
    # Only handle npx commands
    if command not in ("npx", "npx.cmd"):
        return None

    package_name = _extract_package_name(args)
    if not package_name:
        return None

    # Try npm view if npm is available
    npm_path = shutil.which("npm")
    if npm_path:
        try:
            result = subprocess.run(  # noqa: S603
                [npm_path, "view", package_name, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                if version:
                    return version
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fall back to parsing from args
    return _extract_version_from_args(args)


def _get_servers_dir() -> Path:
    """Get the servers cache directory, creating it if needed."""
    servers_dir = get_nomcp_dir() / "servers"
    servers_dir.mkdir(exist_ok=True)
    return servers_dir


def _get_tools_cache_path(server_name: str) -> Path:
    """Get path to the tools cache file for a server."""
    return _get_servers_dir() / f"{server_name}.json"


def load_tools_cache(server_name: str) -> ToolsCache | None:
    """Load cached tools for a server."""
    path = _get_tools_cache_path(server_name)
    if not path.exists():
        return None

    with path.open() as f:
        data = json.load(f)

    return ToolsCache.model_validate(data)


def save_tools_cache(cache: ToolsCache) -> None:
    """Save tools cache to disk."""
    path = _get_tools_cache_path(cache.server_name)
    with path.open("w") as f:
        json.dump(cache.model_dump(mode="json"), f, indent=2)


class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize MCP client.

        Args:
            command: Command to start the server.
            args: Command arguments.
            env: Environment variables.
        """
        self.command = command
        self.args = args or []
        self.env = env

        self._server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )

    async def list_tools(self) -> list[Tool]:
        """Connect to the server and list available tools.

        Returns:
            List of tools from the server.
        """
        async with (
            stdio_client(self._server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
            return list(result.tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool on the server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            Tool result content.

        Raises:
            RuntimeError: If the tool call fails.
        """
        async with (
            stdio_client(self._server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

            if result.isError:
                msg = f"Tool '{tool_name}' failed"
                raise RuntimeError(msg)

            return result.content
