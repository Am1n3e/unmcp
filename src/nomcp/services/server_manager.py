"""Server management service."""

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from nomcp.config import (
    LOGS_DIR,
    find_mcp_config_file,
    get_nomcp_dir,
    get_socket_path,
    load_mcp_config,
)
from nomcp.core import MCPClient, ProcessManager
from nomcp.models import MCPServerConfig, ProcessInfo, ToolsCache
from nomcp.utils import get_package_version, load_tools_cache, save_tools_cache


class InitResult(BaseModel):
    """Result of server initialization."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    server_name: str
    """Name of the initialized server."""

    version: str | None
    """Server package version, if determinable."""

    tools_count: int
    """Number of tools discovered."""

    tools: ToolsCache
    """Cached tools information."""


class ServerManager:
    """Manages MCP server lifecycle."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize server manager.

        Args:
            config_path: Path to config file. If None, searches default locations.
        """
        self.config_path = config_path
        self._process_manager = ProcessManager()

    def list(self) -> dict[str, MCPServerConfig]:
        """List all configured servers.

        Returns:
            Dict mapping server names to their configs.

        Raises:
            FileNotFoundError: If no config file found.
        """
        config = load_mcp_config(self.config_path)
        return dict(config.mcp_servers)

    def get(self, name: str) -> MCPServerConfig:
        """Get configuration for a specific server.

        Args:
            name: Server name.

        Returns:
            Server configuration.

        Raises:
            FileNotFoundError: If no config file found.
            KeyError: If server not found in config.
        """
        servers = self.list()
        if name not in servers:
            msg = f"Server '{name}' not found in config"
            raise KeyError(msg)
        return servers[name]

    def init(self, name: str, *, force: bool = False) -> InitResult:
        """Initialize a server and discover its tools.

        Args:
            name: Server name from config.
            force: If True, reinitialize even if already initialized.

        Returns:
            Initialization result with tools info.

        Raises:
            FileNotFoundError: If no config file found.
            KeyError: If server not found in config.
            RuntimeError: If connection to server fails.
            ValueError: If server is already initialized and force is False.
        """
        if not force and self.is_initialized(name):
            msg = (
                f"Server '{name}' is already initialized. Use --force to reinitialize."
            )
            raise ValueError(msg)

        server_config = self.get(name)

        # Create MCP client and list tools
        client = MCPClient(
            command=server_config.command,
            args=server_config.args,
            env=server_config.env or None,
        )

        try:
            tools = asyncio.run(client.list_tools())
        except Exception as e:
            msg = f"Failed to connect to server '{name}': {e}"
            raise RuntimeError(msg) from e

        # Get version
        version = get_package_version(server_config.command, server_config.args)

        # Save tools cache
        cache = ToolsCache(server_name=name, version=version, tools=tools)
        save_tools_cache(cache)

        return InitResult(
            server_name=name,
            version=version,
            tools_count=len(tools),
            tools=cache,
        )

    def start(self, name: str) -> ProcessInfo:
        """Start a server in persistent mode.

        Spawns a daemon process that maintains the MCP connection and
        listens on a Unix socket for tool call requests.

        Args:
            name: Server name from config.

        Returns:
            Process information for the daemon.

        Raises:
            FileNotFoundError: If no config file found.
            KeyError: If server not found in config.
            RuntimeError: If server is already running.
        """
        # Check if already running
        existing = self._process_manager.get(name)
        if existing is not None:
            msg = f"Server '{name}' is already running (PID: {existing.pid})"
            raise RuntimeError(msg)

        # Get server config
        server_config = self.get(name)

        # Prepare daemon command
        daemon_module = Path(__file__).parent.parent / "core" / "daemon.py"
        daemon_cmd = [
            sys.executable,
            str(daemon_module),
            name,
            server_config.command,
            *server_config.args,
        ]

        # Prepare environment
        process_env = os.environ.copy()
        if server_config.env:
            # Pass server env to daemon via special env var
            process_env["NOMCP_DAEMON_ENV"] = json.dumps(server_config.env)

        # Socket path for this daemon
        socket_path = get_socket_path(name)

        # Log file for daemon stderr
        log_dir = get_nomcp_dir() / LOGS_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"

        # Start daemon process in background (fully detached)
        with log_file.open("w") as stderr_file:
            process = subprocess.Popen(  # noqa: S603
                daemon_cmd,
                env=process_env,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        # Record process info with socket path
        info = ProcessInfo(
            name=name,
            pid=process.pid,
            command=server_config.command,
            args=server_config.args,
            socket_path=socket_path,
        )

        # Register in process manager
        self._process_manager.register(info)

        # Wait for socket to appear (daemon ready)
        import time

        for _ in range(20):  # Wait up to 10 seconds
            time.sleep(0.5)
            if socket_path.exists():
                return info
            if not self._process_manager.is_alive(process.pid):
                break

        # Daemon failed to start - unregister
        self._process_manager.unregister(name)

        # Read error from log file
        error_msg = ""
        if log_file.exists():
            error_msg = log_file.read_text().strip()

        msg = (
            f"Daemon failed to start: {error_msg}"
            if error_msg
            else "Daemon failed to start"
        )
        raise RuntimeError(msg)

    def stop(self, name: str) -> bool:
        """Stop a running server.

        For persistent servers, sends a shutdown message via socket first.

        Args:
            name: Server name.

        Returns:
            True if stopped, False if not running.
        """
        # Check if it's a persistent server with socket
        socket_path = self.get_socket_path(name)
        if socket_path and socket_path.exists():
            # Send shutdown message via socket (may already be closed)
            with contextlib.suppress(Exception):
                self._send_socket_message(socket_path, {"method": "shutdown"})

        return self._process_manager.stop(name)

    def get_socket_path(self, name: str) -> Path | None:
        """Get the socket path for a running persistent server.

        Args:
            name: Server name.

        Returns:
            Socket path if server is running in persistent mode, None otherwise.
        """
        info = self._process_manager.get(name)
        if info is None or info.socket_path is None:
            return None

        if not info.socket_path.exists():
            return None

        return info.socket_path

    def _send_socket_message(self, socket_path: Path, message: dict) -> dict:
        """Send a message to the daemon via socket.

        Args:
            socket_path: Path to the Unix socket.
            message: Message to send.

        Returns:
            Response from daemon.
        """
        import socket

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(socket_path))
            sock.sendall(json.dumps(message).encode() + b"\n")

            # Read response
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break

            return json.loads(response_data.decode().strip())

    def status(self, name: str | None = None) -> dict[str, ProcessInfo | None]:
        """Get status of servers.

        Args:
            name: Specific server name, or None for all.

        Returns:
            Dict mapping server names to process info (None if not running).
        """
        return self._process_manager.status(name)

    def is_initialized(self, name: str) -> bool:
        """Check if a server has been initialized (tools cached).

        Args:
            name: Server name.

        Returns:
            True if initialized.
        """
        return load_tools_cache(name) is not None

    def config_exists(self) -> bool:
        """Check if a config file exists."""
        return find_mcp_config_file() is not None
