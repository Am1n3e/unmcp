"""Tool execution service."""

import asyncio
import json
import socket
from pathlib import Path

from mcp.types import CallToolRequestParams, CallToolResult, TextContent, Tool

from nomcp.core import MCPClient
from nomcp.services.server_manager import ServerManager
from nomcp.utils import load_tools_cache


class ToolRunner:
    """Executes tools on MCP servers."""

    def __init__(self, server_manager: ServerManager | None = None) -> None:
        """Initialize tool runner.

        Args:
            server_manager: Server manager to use. If None, creates one.
        """
        self._server_manager = server_manager

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
        request: CallToolRequestParams,
    ) -> CallToolResult:
        """Call a tool on a server.

        If the server is running in persistent mode (has an active socket),
        the call is routed through the socket. Otherwise, it spawns a new
        MCP server process for the call (on-demand mode).

        Args:
            server: Server name.
            request: Tool call request params with name and arguments.

        Returns:
            Normalized tool result with content and isError fields.

        Raises:
            RuntimeError: If server not initialized or tool call fails.
            KeyError: If server or tool not found.
        """
        # Verify tool exists
        self.get_tool(server, request.name)

        # Check if server has active socket (persistent mode)
        socket_path = self.server_manager.get_socket_path(server)
        if socket_path:
            return self._call_via_socket(socket_path, request)

        # On-demand mode: spawn new process
        return self._call_on_demand(server, request)

    def _call_via_socket(
        self,
        socket_path: Path,
        request: CallToolRequestParams,
    ) -> CallToolResult:
        """Call a tool via Unix socket (persistent mode).

        Args:
            socket_path: Path to the daemon's Unix socket.
            request: Tool call request params with name and arguments.

        Returns:
            Normalized tool result.

        Raises:
            RuntimeError: If the socket communication fails.
        """
        message = {
            "method": "call_tool",
            "name": request.name,
            "arguments": request.arguments,
        }

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(socket_path))
            sock.sendall(json.dumps(message).encode() + b"\n")

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
            # Return error as content
            return CallToolResult(
                content=[TextContent(type="text", text=response["error"])],
                isError=True,
            )

        return CallToolResult.model_validate(response)

    def _call_on_demand(
        self,
        server: str,
        request: CallToolRequestParams,
    ) -> CallToolResult:
        """Call a tool by spawning a new MCP server (on-demand mode).

        Args:
            server: Server name.
            request: Tool call request params with name and arguments.

        Returns:
            Normalized tool result.
        """
        # Get server config
        server_config = self.server_manager.get(server)

        # Create client and call tool
        client = MCPClient(
            command=server_config.command,
            args=server_config.args,
            env=server_config.env or None,
        )

        return asyncio.run(client.call_tool_raw(request))
