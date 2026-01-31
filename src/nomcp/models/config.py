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


class ServerSettings(BaseModel):
    """Per-server settings."""

    dump_threshold: int | None = None
    dump_call_args: bool | None = None  # None = use global


class NoMCPSettings(BaseModel):
    """noMCP-specific settings."""

    dump_dir: str = "nomcp_output"
    dump_threshold: int | None = None  # None = disabled globally
    dump_call_args: bool = True  # Default: include call args
    servers: dict[str, ServerSettings] = {}

    def get_dump_threshold(self, server_name: str) -> int | None:
        """Get effective dump threshold for a server (per-server overrides global)."""
        server = self.servers.get(server_name)
        if server and server.dump_threshold is not None:
            return server.dump_threshold
        return self.dump_threshold

    def get_dump_call_args(self, server_name: str) -> bool:
        """Get effective dump_call_args for a server (per-server overrides global)."""
        server = self.servers.get(server_name)
        if server and server.dump_call_args is not None:
            return server.dump_call_args
        return self.dump_call_args
