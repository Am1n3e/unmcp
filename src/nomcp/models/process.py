"""Process management models."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    """Information about a running MCP server process."""

    name: str
    """Server name."""

    pid: int
    """Process ID."""

    command: str
    """Command used to start the server."""

    args: list[str] = Field(default_factory=list)
    """Command arguments."""

    started_at: datetime = Field(default_factory=datetime.now)
    """When the process was started."""

    socket_path: Path | None = None
    """Path to Unix socket for persistent mode. None for on-demand processes."""
