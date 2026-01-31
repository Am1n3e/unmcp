"""CLI entry point for noMCP."""

import json
from typing import Any

import click

from nomcp import __version__


class DynamicServerGroup(click.Group):
    """Custom group that handles dynamic server/tool commands."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # First check built-in commands
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd

        # Check if it's a server name
        from nomcp.mcp_client import load_tools_cache

        cache = load_tools_cache(cmd_name)
        if cache is None:
            return None

        # Create dynamic group for this server
        return self._create_server_group(cmd_name, cache)

    def _create_server_group(
        self, server_name: str, cache: Any
    ) -> click.Group:
        """Create a dynamic command group for a server."""

        @click.group(name=server_name, help=f"Tools for {server_name} server")
        def server_group() -> None:
            pass

        # Add each tool as a subcommand
        for tool in cache.tools:
            cmd = self._create_tool_command(server_name, tool)
            server_group.add_command(cmd)

        return server_group

    def _create_tool_command(self, server_name: str, tool: Any) -> click.Command:
        """Create a Click command for a tool."""
        from nomcp.services import ToolRunner

        # Build parameters from input schema
        params = self._build_params_from_schema(tool.inputSchema)

        @click.pass_context
        def tool_callback(ctx: click.Context, **kwargs: Any) -> None:
            # Filter out None values
            arguments = {k: v for k, v in kwargs.items() if v is not None}

            runner = ToolRunner()
            try:
                result = runner.call(server_name, tool.name, arguments or None)
                self._print_result(result)
            except (RuntimeError, KeyError) as e:
                click.echo(f"Error: {e}", err=True)
                raise SystemExit(1) from None

        return click.Command(
            name=tool.name,
            help=tool.description or f"Call {tool.name} tool",
            params=params,
            callback=tool_callback,
        )

    def _build_params_from_schema(self, schema: dict[str, Any]) -> list[click.Parameter]:
        """Build Click parameters from JSON schema."""
        params: list[click.Parameter] = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            description = prop_schema.get("description", "")
            is_required = prop_name in required
            default = prop_schema.get("default")

            # Map JSON schema types to Click types
            click_type: Any = str
            if prop_type == "integer":
                click_type = int
            elif prop_type == "number":
                click_type = float
            elif prop_type == "boolean":
                click_type = bool
            elif prop_type in ("array", "object"):
                click_type = str  # Accept as JSON string

            # Handle enums
            if "enum" in prop_schema:
                click_type = click.Choice(prop_schema["enum"])

            params.append(
                click.Option(
                    [f"--{prop_name.replace('_', '-')}"],
                    type=click_type,
                    required=is_required,
                    default=default,
                    help=description,
                )
            )

        return params

    def _print_result(self, result: Any) -> None:
        """Print tool result to console."""
        if isinstance(result, list):
            for item in result:
                if hasattr(item, "text"):
                    click.echo(item.text)
                elif hasattr(item, "data"):
                    click.echo(f"[Binary data: {len(item.data)} bytes]")
                else:
                    click.echo(str(item))
        else:
            click.echo(json.dumps(result, indent=2) if isinstance(result, dict) else str(result))

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List all commands including dynamic server commands."""
        commands = list(super().list_commands(ctx))

        # Add initialized servers
        from nomcp.config import get_nomcp_dir

        servers_dir = get_nomcp_dir() / "servers"
        if servers_dir.exists():
            for path in servers_dir.glob("*.json"):
                server_name = path.stem
                if server_name not in commands:
                    commands.append(server_name)

        return sorted(commands)


@click.group(cls=DynamicServerGroup)
@click.version_option(version=__version__, prog_name="nomcp")
def main() -> None:
    """noMCP - CLI interface for MCP servers."""


# =============================================================================
# clt - Server management commands
# =============================================================================


@main.group()
def clt() -> None:
    """Server management commands."""


@clt.command()
@click.argument("server")
@click.option("--force", is_flag=True, help="Reinitialize even if already initialized.")
def init(server: str, force: bool) -> None:
    """Initialize an MCP server and discover its tools.

    SERVER is the name of the server defined in the config file.
    """
    from nomcp.services import ServerManager

    manager = ServerManager()

    if not manager.config_exists():
        click.echo("Error: No configuration file found")
        raise SystemExit(1)

    try:
        result = manager.init(server, force=force)
    except (KeyError, ValueError, RuntimeError) as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from None

    version_str = f" (v{result.version})" if result.version else ""
    click.echo(f"Initialized server: {server}{version_str}")
    click.echo(f"Discovered {result.tools_count} tools:")
    for tool in result.tools.tools:
        click.echo(f"  - {tool.name}: {tool.description or '(no description)'}")


@clt.command()
@click.argument("server")
def start(server: str) -> None:
    """Start an MCP server in persistent mode.

    Starts a daemon that maintains the MCP connection, allowing tool calls
    to reuse the same server process instead of spawning new ones.

    SERVER is the name of the server defined in the config file.
    """
    from nomcp.services import ServerManager

    manager = ServerManager()

    if not manager.config_exists():
        click.echo("Error: No configuration file found", err=True)
        raise SystemExit(1)

    if not manager.is_initialized(server):
        click.echo(f"Error: Server '{server}' not initialized. Run: nomcp clt init {server}", err=True)
        raise SystemExit(1)

    try:
        info = manager.start(server)
    except (KeyError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    click.echo(f"Started server: {server} (PID: {info.pid})")
    if info.socket_path:
        click.echo(f"Socket: {info.socket_path}")


@clt.command()
@click.argument("server")
def stop(server: str) -> None:
    """Stop a running MCP server.

    SERVER is the name of the server to stop.
    """
    from nomcp.services import ServerManager

    manager = ServerManager()

    if manager.stop(server):
        click.echo(f"Stopped server: {server}")
    else:
        click.echo(f"Server '{server}' is not running")


@clt.command()
@click.argument("server", required=False)
def status(server: str | None) -> None:
    """Show status of MCP servers.

    SERVER is optional. If provided, shows status of that server only.
    """
    from nomcp.services import ServerManager

    manager = ServerManager()
    statuses = manager.status(server)

    if not statuses:
        click.echo("No servers registered")
        return

    for name, info in statuses.items():
        if info:
            mode = "persistent" if info.socket_path else "running"
            click.echo(f"{name}: {mode} (PID: {info.pid})")
        else:
            click.echo(f"{name}: stopped")


@clt.command(name="list")
def list_servers() -> None:
    """List configured MCP servers."""
    from nomcp.services import ServerManager

    manager = ServerManager()

    if not manager.config_exists():
        click.echo("No configuration file found")
        return

    try:
        servers = manager.list()
    except FileNotFoundError:
        click.echo("No configuration file found")
        return

    if not servers:
        click.echo("No servers configured")
        return

    # Get status for all servers
    statuses = manager.status()

    # Build table data
    rows = []
    for name, config in servers.items():
        status = "running" if statuses.get(name) else "stopped"
        command = f"{config.command} {' '.join(config.args)}"
        rows.append((name, status, command))

    # Calculate column widths
    name_width = max(len("NAME"), max(len(r[0]) for r in rows))
    status_width = max(len("STATUS"), max(len(r[1]) for r in rows))

    # Print table header
    header = f"{'NAME':<{name_width}}  {'STATUS':<{status_width}}  COMMAND"
    click.echo(header)
    click.echo("-" * len(header))

    # Print rows
    for name, status, command in rows:
        click.echo(f"{name:<{name_width}}  {status:<{status_width}}  {command}")


if __name__ == "__main__":
    main()
