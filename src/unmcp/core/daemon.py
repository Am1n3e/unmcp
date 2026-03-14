"""Daemon for persistent MCP server connections.

This module provides a stdio-to-socket proxy daemon that bridges MCP's stdio
transport to a Unix socket, allowing multiple CLI invocations to reuse the
same MCP server connection.
"""

import asyncio
import base64
import json
import os
import signal
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolRequestParams

from unmcp.config import get_socket_path


class DaemonServer:
    """Unix socket server that proxies requests to an MCP server."""

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize daemon server.

        Args:
            server_name: Name of the MCP server.
            command: Command to start the MCP server.
            args: Arguments for the command.
            env: Environment variables for the server.
        """
        self.server_name = server_name
        self.command = command
        self.args = args
        self.env = env
        self.socket_path = get_socket_path(server_name)
        self._server: asyncio.Server | None = None
        self._session: ClientSession | None = None
        self._shutdown_event = asyncio.Event()
        self._stdio_context: Any = None
        self._session_context: Any = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        try:
            while True:
                # Read request (newline-delimited JSON)
                line = await reader.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.decode())
                except json.JSONDecodeError as e:
                    response = {"error": f"Invalid JSON: {e}"}
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
                    continue

                # Handle request
                response = await self._handle_request(request)
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()

        except asyncio.CancelledError:
            # Expected during normal task cancellation; connection cleanup is handled in finally.
            pass
        except Exception as e:
            # Log error but don't crash the server
            print(f"Client handler error: {e}", file=sys.stderr)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a single request.

        Args:
            request: JSON request with method, tool, and args.

        Returns:
            JSON response.
        """
        method = request.get("method")

        if method == "call_tool":
            tool_request = CallToolRequestParams(
                name=request.get("name", ""),
                arguments=request.get("arguments"),
            )
            return await self._call_tool(tool_request)
        elif method == "list_tools":
            return await self._list_tools()
        elif method == "shutdown":
            self._shutdown_event.set()
            return {"status": "shutting_down"}
        elif method == "ping":
            return {"status": "ok"}
        else:
            return {"error": f"Unknown method: {method}"}

    async def _call_tool(
        self,
        request: CallToolRequestParams,
    ) -> dict[str, Any]:
        """Call a tool via the MCP session.

        Args:
            request: Tool call request params with name and arguments.

        Returns:
            Tool result or error.
        """
        if self._session is None:
            return {"error": "Session not initialized"}

        try:
            result = await self._session.call_tool(request.name, request.arguments)

            # Serialize content for JSON transport
            content = []
            for item in result.content:
                if hasattr(item, "text"):
                    content.append({"type": "text", "text": item.text})
                elif hasattr(item, "data"):
                    # Base64-encode binary data for JSON transport
                    data = item.data
                    if isinstance(data, bytes):
                        data = base64.b64encode(data).decode("ascii")
                    content.append(
                        {
                            "type": "binary",
                            "data": data,
                            "encoding": "base64",
                            "mimeType": getattr(
                                item, "mimeType", "application/octet-stream"
                            ),
                        }
                    )
                else:
                    content.append({"type": "unknown", "value": str(item)})

            return {"content": content, "isError": result.isError}

        except Exception as e:
            return {"error": str(e), "isError": True}

    async def _list_tools(self) -> dict[str, Any]:
        """List available tools.

        Returns:
            List of tools or error.
        """
        if self._session is None:
            return {"error": "Session not initialized"}

        try:
            result = await self._session.list_tools()
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]
            return {"tools": tools}
        except Exception as e:
            return {"error": str(e)}

    async def run(self) -> None:
        """Run the daemon server."""
        # Clean up any stale socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        # Set up MCP server connection
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )

        try:
            # Start MCP server and maintain session
            async with (
                stdio_client(server_params) as (read, write),
                ClientSession(read, write) as session,
            ):
                self._session = session
                await session.initialize()

                # Start Unix socket server
                self._server = await asyncio.start_unix_server(
                    self._handle_client,
                    path=str(self.socket_path),
                )

                # Make socket accessible
                self.socket_path.chmod(0o600)

                print(f"Daemon started for {self.server_name}", file=sys.stderr)
                print(f"Socket: {self.socket_path}", file=sys.stderr)

                # Wait for shutdown signal
                await self._shutdown_event.wait()

        finally:
            # Cleanup
            if self._server:
                self._server.close()
                await self._server.wait_closed()

            if self.socket_path.exists():
                self.socket_path.unlink()

            print(f"Daemon stopped for {self.server_name}", file=sys.stderr)


async def run_daemon(
    server_name: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> None:
    """Run the daemon for a server.

    Args:
        server_name: Name of the MCP server.
        command: Command to start the MCP server.
        args: Arguments for the command.
        env: Environment variables for the server.
    """
    daemon = DaemonServer(server_name, command, args, env)
    await daemon.run()


def main() -> None:
    """Entry point for the daemon process.

    Expects command-line args: server_name command [args...]
    Environment variables are passed through.
    """
    if len(sys.argv) < 3:
        print("Usage: daemon.py <server_name> <command> [args...]", file=sys.stderr)
        sys.exit(1)

    server_name = sys.argv[1]
    command = sys.argv[2]
    args = sys.argv[3:]

    # Get env from environment variable if set
    env_json = os.environ.get("UNMCP_DAEMON_ENV")
    env = json.loads(env_json) if env_json else None

    asyncio.run(run_daemon(server_name, command, args, env))


if __name__ == "__main__":
    main()
