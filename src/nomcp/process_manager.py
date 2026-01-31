"""Process management for MCP servers."""

import contextlib
import json
import os
import signal
import subprocess

from nomcp.config import get_nomcp_dir
from nomcp.models import ProcessInfo, ProcessRegistry

PROCESSES_FILE = "processes.json"


class ProcessManager:
    """Manages MCP server processes."""

    def __init__(self) -> None:
        """Initialize process manager."""
        self._registry_path = get_nomcp_dir() / PROCESSES_FILE

    def _load_registry(self) -> ProcessRegistry:
        """Load the process registry from disk."""
        if not self._registry_path.exists():
            return ProcessRegistry()

        with self._registry_path.open() as f:
            data = json.load(f)

        return ProcessRegistry.model_validate(data)

    def _save_registry(self, registry: ProcessRegistry) -> None:
        """Save the process registry to disk."""
        with self._registry_path.open("w") as f:
            json.dump(registry.model_dump(mode="json"), f, indent=2)

    @staticmethod
    def is_alive(pid: int) -> bool:
        """Check if a process is still running."""
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def start(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessInfo:
        """Start a new MCP server process.

        Args:
            name: Name of the server.
            command: Command to run.
            args: Command arguments.
            env: Additional environment variables.

        Returns:
            Information about the started process.

        Raises:
            RuntimeError: If process is already running.
        """
        args = args or []
        registry = self._load_registry()

        # Check if already running
        if name in registry.processes:
            existing = registry.processes[name]
            if self.is_alive(existing.pid):
                msg = f"Server '{name}' is already running (PID: {existing.pid})"
                raise RuntimeError(msg)
            # Clean up stale entry
            del registry.processes[name]

        # Merge environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        # Start the process
        process = subprocess.Popen(  # noqa: S603
            [command, *args],
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        # Record process info
        info = ProcessInfo(
            name=name,
            pid=process.pid,
            command=command,
            args=args,
        )

        registry.processes[name] = info
        self._save_registry(registry)

        return info

    def stop(self, name: str) -> bool:
        """Stop a running MCP server process.

        Args:
            name: Name of the server to stop.

        Returns:
            True if process was stopped, False if not found.
        """
        registry = self._load_registry()

        if name not in registry.processes:
            return False

        info = registry.processes[name]

        if self.is_alive(info.pid):
            with contextlib.suppress(OSError):
                os.kill(info.pid, signal.SIGTERM)

        del registry.processes[name]
        self._save_registry(registry)

        return True

    def status(self, name: str | None = None) -> dict[str, ProcessInfo | None]:
        """Get status of running processes.

        Args:
            name: Specific server name, or None for all.

        Returns:
            Dict mapping server names to their info (None if not running).
        """
        registry = self._load_registry()
        result: dict[str, ProcessInfo | None] = {}

        if name:
            if name in registry.processes:
                info = registry.processes[name]
                result[name] = info if self.is_alive(info.pid) else None
            else:
                result[name] = None
        else:
            for server_name, info in registry.processes.items():
                result[server_name] = info if self.is_alive(info.pid) else None

        return result

    def get(self, name: str) -> ProcessInfo | None:
        """Get info for a specific process.

        Args:
            name: Name of the server.

        Returns:
            Process info if running, None otherwise.
        """
        registry = self._load_registry()

        if name not in registry.processes:
            return None

        info = registry.processes[name]
        return info if self.is_alive(info.pid) else None

    def cleanup(self) -> int:
        """Remove stale entries from the registry.

        Returns:
            Number of stale entries removed.
        """
        registry = self._load_registry()
        stale = [
            name
            for name, info in registry.processes.items()
            if not self.is_alive(info.pid)
        ]

        for name in stale:
            del registry.processes[name]

        if stale:
            self._save_registry(registry)

        return len(stale)
