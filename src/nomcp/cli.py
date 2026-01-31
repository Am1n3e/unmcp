"""CLI entry point for noMCP."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from mcp.types import CallToolRequestParams, CallToolResult

from nomcp import __version__


class DynamicServerGroup(click.Group):
    """Custom group that handles dynamic server/tool commands."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # First check built-in commands
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd

        # Check if it's a server name
        from nomcp.utils import load_tools_cache

        cache = load_tools_cache(cmd_name)
        if cache is None:
            return None

        # Create dynamic group for this server
        return self._create_server_group(cmd_name, cache)

    def _has_nested_args(self, schema: dict[str, Any]) -> bool:
        """Check if schema has object or array type properties."""
        properties = schema.get("properties", {})
        for prop_schema in properties.values():
            if prop_schema.get("type") in ("array", "object"):
                return True
        return False

    def _create_server_group(
        self, server_name: str, cache: Any
    ) -> click.Group:
        """Create a dynamic command group for a server."""

        @click.group(name=server_name, help=f"Tools for {server_name} server")
        @click.option("--json", "json_output", is_flag=True, help="Output raw JSON response.")
        @click.option("--output", "output_path", type=click.Path(), help="Write JSON result to file.")
        @click.pass_context
        def server_group(ctx: click.Context, json_output: bool, output_path: str | None) -> None:
            if json_output and output_path:
                raise click.UsageError("--json and --output are mutually exclusive.")
            ctx.ensure_object(dict)
            ctx.obj["json_output"] = json_output
            ctx.obj["output_path"] = output_path

        # Add each tool as a subcommand (skip tools with nested args)
        for tool in cache.tools:
            if self._has_nested_args(tool.inputSchema):
                continue  # Skip tools with nested args
            cmd = self._create_tool_command(server_name, tool)
            server_group.add_command(cmd)

        return server_group

    def _map_arguments(
        self, kwargs: dict[str, Any], name_mapping: dict[str, str]
    ) -> dict[str, Any]:
        """Map Click kwargs to MCP argument names, filtering None values."""
        arguments = {}
        for click_name, value in kwargs.items():
            if value is not None:
                mcp_name = name_mapping.get(click_name, click_name)
                arguments[mcp_name] = value
        return arguments

    def _create_tool_command(self, server_name: str, tool: Any) -> click.Command:
        """Create a Click command for a tool."""
        from nomcp.services import ToolRunner

        # Build parameters from input schema
        params, name_mapping = self._build_params_from_schema(tool.inputSchema)

        @click.pass_context
        def tool_callback(ctx: click.Context, **kwargs: Any) -> None:
            json_output = ctx.obj.get("json_output", False)
            output_path = ctx.obj.get("output_path")
            arguments = self._map_arguments(kwargs, name_mapping)

            # Resolve output_path if it's a directory
            if output_path:
                output_path = self._resolve_output_path(output_path, server_name, tool.name)

            runner = ToolRunner()
            try:
                request = CallToolRequestParams(
                    name=tool.name, arguments=arguments or None
                )
                result = runner.call(server_name, request)
            except (RuntimeError, KeyError, ValueError) as e:
                click.echo(f"Error: {e}", err=True)
                raise SystemExit(1) from None

            is_error = result.isError or False

            # Check for auto-dump if no explicit output and no error
            auto_dump_path, dump_threshold = None, None
            if not output_path and not is_error:
                auto_dump_path, dump_threshold = self._get_auto_dump_path(
                    server_name, tool.name, result
                )

            # Use auto_dump_path if triggered, otherwise use explicit output_path
            effective_output_path = output_path or auto_dump_path

            # Handle file output (explicit or auto-dump)
            if effective_output_path:
                self._write_result_to_file(
                    result,
                    effective_output_path,
                    is_error,
                    auto_dump_path,
                    dump_threshold,
                    server_name,
                    tool.name,
                    arguments,
                )
                return

            # Handle error for non-file output
            if is_error:
                if json_output:
                    result_dict = result.model_dump(mode="json", exclude_none=True)
                    click.echo(json.dumps(result_dict, indent=2))
                else:
                    for item in result.content:
                        if hasattr(item, "text"):
                            click.echo(f"Error: {item.text}", err=True)
                raise SystemExit(1)

            self._print_result(result, json_output=json_output)

        return click.Command(
            name=tool.name,
            help=tool.description or f"Call {tool.name} tool",
            params=params,
            callback=tool_callback,
        )

    def _build_params_from_schema(
        self, schema: dict[str, Any]
    ) -> tuple[list[click.Parameter], dict[str, str]]:
        """Build Click parameters from JSON schema.

        Returns:
            Tuple of (parameters, name_mapping) where name_mapping maps
            Click's lowercased param names back to original MCP property names.
        """
        params: list[click.Parameter] = []
        name_mapping: dict[str, str] = {}  # click_name -> mcp_name
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
                raise NotImplementedError(
                    f"Nested arguments (type '{prop_type}') are not yet supported"
                )

            # Handle enums
            if "enum" in prop_schema:
                click_type = click.Choice(prop_schema["enum"])

            # Click lowercases option names, track the mapping
            click_param_name = prop_name.lower().replace("-", "_")
            name_mapping[click_param_name] = prop_name

            params.append(
                click.Option(
                    [f"--{prop_name.replace('_', '-')}"],
                    type=click_type,
                    required=is_required,
                    default=default,
                    help=description,
                )
            )

        return params, name_mapping

    def _estimate_tokens(self, result: CallToolResult) -> int:
        """Estimate token count from result content."""
        total_chars = 0
        for item in result.content:
            if hasattr(item, "text"):
                total_chars += len(item.text)
        return total_chars // 4  # Rough estimate: ~4 chars per token

    def _get_auto_dump_path(
        self, server_name: str, tool_name: str, result: CallToolResult
    ) -> tuple[str | None, int | None]:
        """Check if result should be auto-dumped based on settings.

        Returns:
            Tuple of (dump_path, threshold) if auto-dump triggered, (None, None) otherwise.
        """
        from nomcp.config import load_settings

        settings = load_settings()
        dump_threshold = settings.get_dump_threshold(server_name)

        if not dump_threshold:
            return None, None

        estimated_tokens = self._estimate_tokens(result)
        if estimated_tokens <= dump_threshold:
            return None, None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{server_name}_{tool_name}_{timestamp}.json"
        dump_dir = Path(settings.dump_dir)
        dump_dir.mkdir(parents=True, exist_ok=True)
        return str(dump_dir / filename), dump_threshold

    def _resolve_output_path(
        self, output_path: str, server_name: str, tool_name: str
    ) -> str:
        """Resolve output path, generating filename if path is a directory."""
        path = Path(output_path)
        if path.is_dir():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{server_name}_{tool_name}_{timestamp}.json"
            return str(path / filename)
        return output_path

    def _write_result_to_file(
        self,
        result: CallToolResult,
        output_path: str,
        is_error: bool,
        auto_dump_path: str | None,
        dump_threshold: int | None,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Write result to file and print status message."""
        from nomcp.config import load_settings

        settings = load_settings()
        dump_call_args = settings.get_dump_call_args(server_name)

        result_dict = result.model_dump(mode="json", exclude_none=True)
        if dump_call_args:
            output_data: Any = {
                "tool_call": {
                    "server": server_name,
                    "tool": tool_name,
                    "arguments": arguments,
                },
                "response": result_dict,
            }
        else:
            output_data = result_dict

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        if is_error:
            click.echo(f"Failed: {output_path}", err=True)
            raise SystemExit(1)
        click.echo("Tool executed successfully.")
        if auto_dump_path:
            click.echo(
                f"Response exceeded {dump_threshold} tokens, auto-dumped to: {output_path}"
            )
        else:
            click.echo(f"Tool output written to: {output_path}")

    def _print_result(self, result: CallToolResult, json_output: bool = False) -> None:
        """Print tool result to console."""
        if json_output:
            result_dict = result.model_dump(mode="json", exclude_none=True)
            click.echo(json.dumps(result_dict, indent=2))
            return

        for item in result.content:
            if hasattr(item, "text"):
                click.echo(item.text)
            elif hasattr(item, "mimeType"):
                click.echo(f"[Image: {item.mimeType}]")
            else:
                click.echo(str(item))

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

    def _get_server_names(self) -> list[str]:
        """Get list of initialized server names."""
        from nomcp.config import get_nomcp_dir

        servers_dir = get_nomcp_dir() / "servers"
        if not servers_dir.exists():
            return []
        return [p.stem for p in servers_dir.glob("*.json")]

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Format commands into separate sections."""
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        server_names = set(self._get_server_names())
        builtin_cmds = [(name, cmd) for name, cmd in commands if name not in server_names]
        server_cmds = [(name, cmd) for name, cmd in commands if name in server_names]

        # Built-in commands
        if builtin_cmds:
            with formatter.section("Commands"):
                formatter.write_dl([
                    (name, cmd.get_short_help_str(limit=formatter.width))
                    for name, cmd in builtin_cmds
                ])

        # Server commands
        if server_cmds:
            with formatter.section("Servers"):
                formatter.write_dl([
                    (name, cmd.get_short_help_str(limit=formatter.width))
                    for name, cmd in server_cmds
                ])


@click.group(
    cls=DynamicServerGroup,
    epilog="""\
Use 'nomcp clt --help' for server management.

Use 'nomcp <server> --help' for server tools.""",
)
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
