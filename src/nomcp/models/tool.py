"""Tool cache models."""

from mcp.types import Tool
from pydantic import BaseModel, ConfigDict, Field


class ToolsCache(BaseModel):
    """Cached tools for an MCP server."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    server_name: str
    """Name of the MCP server."""

    version: str | None = None
    """Version of the MCP server package, if determinable."""

    tools: list[Tool] = Field(default_factory=list)
    """List of tools available on the server."""
