"""Configuration models."""

from pydantic import BaseModel, ConfigDict, Field


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str
    """Command to start the MCP server."""

    args: list[str] = Field(default_factory=list)
    """Arguments for the command."""

    env: dict[str, str] = Field(default_factory=dict)
    """Environment variables for the server."""


class UnmcpConfig(BaseModel):
    """Root configuration model."""

    mcp_servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict, alias="mcpServers"
    )
    """Map of server names to their configurations."""


class ServerSettings(BaseModel):
    """Per-server settings."""

    dump_threshold: int | None = None
    """Token threshold for auto-dumping. None means use global setting."""

    dump_call_args: bool | None = None
    """Whether to include call args in dumps. None means use global setting."""


class UnmcpSettings(BaseModel):
    """unmcp settings."""

    model_config = ConfigDict(validate_default=True)

    dump_dir: str = "unmcp_output"
    """Directory for auto-dumped output files."""

    dump_threshold: int | None = None
    """Global token threshold for auto-dumping. None means disabled."""

    dump_call_args: bool = True
    """Whether to include call args in dumps by default."""

    servers: dict[str, ServerSettings] = Field(default_factory=dict)
    """Per-server settings overrides."""

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
