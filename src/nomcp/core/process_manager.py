"""Process management for MCP servers."""

import contextlib
import json
import os
import signal
from pathlib import Path

from nomcp.config import PROCESSES_DIR, get_nomcp_dir
from nomcp.models import ProcessInfo


class ProcessManager:
    """Manages MCP server processes."""

    def __init__(self) -> None:
        """Initialize process manager."""
        self._processes_dir = get_nomcp_dir() / PROCESSES_DIR

    def _get_process_path(self, name: str) -> Path:
        """Get the path to a process file."""
        return self._processes_dir / f"{name}.json"

    @staticmethod
    def is_alive(pid: int) -> bool:
        """Check if a process is still running."""
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def register(self, info: ProcessInfo) -> None:
        """Register a process in the registry.

        Args:
            info: Process information to register.
        """
        self._processes_dir.mkdir(parents=True, exist_ok=True)
        path = self._get_process_path(info.name)
        with path.open("w") as f:
            json.dump(info.model_dump(mode="json"), f, indent=2, default=str)

    def unregister(self, name: str) -> bool:
        """Remove a process from the registry.

        Args:
            name: Name of the server to unregister.

        Returns:
            True if removed, False if not found.
        """
        path = self._get_process_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def stop(self, name: str) -> bool:
        """Stop a running MCP server process.

        Args:
            name: Name of the server to stop.

        Returns:
            True if process was stopped, False if not found.
        """
        path = self._get_process_path(name)
        if not path.exists():
            return False

        with path.open() as f:
            data = json.load(f)
        info = ProcessInfo.model_validate(data)

        if self.is_alive(info.pid):
            with contextlib.suppress(OSError):
                os.kill(info.pid, signal.SIGTERM)

        path.unlink()
        return True

    def status(self, name: str | None = None) -> dict[str, ProcessInfo | None]:
        """Get status of running processes.

        Args:
            name: Specific server name, or None for all.

        Returns:
            Dict mapping server names to their info (None if not running).
        """
        result: dict[str, ProcessInfo | None] = {}

        if name:
            path = self._get_process_path(name)
            if path.exists():
                with path.open() as f:
                    data = json.load(f)
                info = ProcessInfo.model_validate(data)
                result[name] = info if self.is_alive(info.pid) else None
            else:
                result[name] = None
        else:
            if self._processes_dir.exists():
                for path in self._processes_dir.glob("*.json"):
                    server_name = path.stem
                    with path.open() as f:
                        data = json.load(f)
                    info = ProcessInfo.model_validate(data)
                    result[server_name] = info if self.is_alive(info.pid) else None

        return result

    def get(self, name: str) -> ProcessInfo | None:
        """Get info for a specific process.

        Args:
            name: Name of the server.

        Returns:
            Process info if running, None otherwise.
        """
        path = self._get_process_path(name)
        if not path.exists():
            return None

        with path.open() as f:
            data = json.load(f)
        info = ProcessInfo.model_validate(data)
        return info if self.is_alive(info.pid) else None

    def cleanup(self) -> int:
        """Remove stale entries from the registry.

        Returns:
            Number of stale entries removed.
        """
        if not self._processes_dir.exists():
            return 0

        stale_count = 0
        for path in self._processes_dir.glob("*.json"):
            with path.open() as f:
                data = json.load(f)
            info = ProcessInfo.model_validate(data)
            if not self.is_alive(info.pid):
                path.unlink()
                stale_count += 1

        return stale_count
