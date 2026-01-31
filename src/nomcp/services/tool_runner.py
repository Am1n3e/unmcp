"""Tool execution service."""

import asyncio
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from nomcp.mcp_client import MCPClient, load_tools_cache
from nomcp.services.server_manager import ServerManager


@dataclass
class ToolRunner:
    """Executes tools on MCP servers."""

    _server_manager: ServerManager | None = None

    @property
    def server_manager(self) -> ServerManager:
        """Get or create server manager."""
        if self._server_manager is None:
            self._server_manager = ServerManager()
        return self._server_manager

    def get_tools(self, server: str) -> list[Tool]:
        """Get available tools for a server.

        Args:
            server: Server name.

        Returns:
            List of tools.

        Raises:
            RuntimeError: If server not initialized.
        """
        cache = load_tools_cache(server)
        if cache is None:
            msg = f"Server '{server}' not initialized. Run: nomcp clt init {server}"
            raise RuntimeError(msg)
        return cache.tools

    def get_tool(self, server: str, tool_name: str) -> Tool:
        """Get a specific tool by name.

        Args:
            server: Server name.
            tool_name: Tool name.

        Returns:
            Tool definition.

        Raises:
            RuntimeError: If server not initialized.
            KeyError: If tool not found.
        """
        tools = self.get_tools(server)
        for tool in tools:
            if tool.name == tool_name:
                return tool
        msg = f"Tool '{tool_name}' not found on server '{server}'"
        raise KeyError(msg)

    def call(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool on a server.

        If the server is running in persistent mode (has an active socket),
        the call is routed through the socket. Otherwise, it spawns a new
        MCP server process for the call (on-demand mode).

        Args:
            server: Server name.
            tool_name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result content.

        Raises:
            RuntimeError: If server not initialized or tool call fails.
            KeyError: If server or tool not found.
        """
        # Verify tool exists
        self.get_tool(server, tool_name)

        # Check if server has active socket (persistent mode)
        socket_path = self.server_manager.get_socket_path(server)
        if socket_path:
            return self._call_via_socket(socket_path, tool_name, arguments)

        # On-demand mode: spawn new process
        return self._call_on_demand(server, tool_name, arguments)

    def _call_via_socket(
        self,
        socket_path: Path,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        """Call a tool via Unix socket (persistent mode).

        Args:
            socket_path: Path to the daemon's Unix socket.
            tool_name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result content.

        Raises:
            RuntimeError: If the tool call fails.
        """
        request = {
            "method": "call_tool",
            "name": tool_name,
            "arguments": arguments,
        }

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(socket_path))
            sock.sendall(json.dumps(request).encode() + b"\n")

            # Read response (newline-delimited JSON)
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break

        response = json.loads(response_data.decode().strip())

        if "error" in response:
            raise RuntimeError(response["error"])

        # Convert serialized content back to MCP types
        content = []
        for item in response.get("content", []):
            if item.get("type") == "text":
                content.append(TextContent(type="text", text=item["text"]))
            else:
                # For other types, return raw dict
                content.append(item)

        return content

    def _call_on_demand(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        """Call a tool by spawning a new MCP server (on-demand mode).

        Args:
            server: Server name.
            tool_name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result content.
        """
        # Get server config
        server_config = self.server_manager.get(server)

        # Create client and call tool
        client = MCPClient(
            command=server_config.command,
            args=server_config.args,
            env=server_config.env or None,
        )

        return asyncio.run(client.call_tool(tool_name, arguments))
