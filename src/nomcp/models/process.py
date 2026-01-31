"""Process management models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    """Information about a running MCP server process."""

    name: str
    pid: int
    command: str
    args: list[str] = []
    started_at: datetime = Field(default_factory=datetime.now)
    socket_path: str | None = None


class ProcessRegistry(BaseModel):
    """Registry of all running processes."""

    processes: dict[str, ProcessInfo] = {}
