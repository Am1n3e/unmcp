"""Configuration models."""

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str
    args: list[str] = []
    env: dict[str, str] = {}


class NoMCPConfig(BaseModel):
    """Root configuration model."""

    mcp_servers: dict[str, MCPServerConfig] = Field(
        default={}, alias="mcpServers"
    )
