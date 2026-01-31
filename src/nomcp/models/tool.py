"""Tool cache models."""

from mcp.types import Tool
from pydantic import BaseModel


class ToolsCache(BaseModel):
    """Cached tools for an MCP server."""

    server_name: str
    version: str | None = None
    tools: list[Tool] = []

    class Config:
        arbitrary_types_allowed = True
