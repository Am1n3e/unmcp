"""MCP client for communicating with MCP servers."""

from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolRequestParams, Tool


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
        request: CallToolRequestParams,
    ) -> Any:
        """Call a tool on the server.

        Args:
            request: Tool call request params with name and arguments.

        Returns:
            Tool result content.

        Raises:
            RuntimeError: If the tool call fails.
        """
        result = await self.call_tool_raw(request)

        if result.isError:
            msg = f"Tool '{request.name}' failed"
            raise RuntimeError(msg)

        return result.content

    async def call_tool_raw(
        self,
        request: CallToolRequestParams,
    ) -> Any:
        """Call a tool on the server and return the full result.

        Args:
            request: Tool call request params with name and arguments.

        Returns:
            Full CallToolResult including content and isError.
        """
        async with (
            stdio_client(self._server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await session.call_tool(request.name, request.arguments)
