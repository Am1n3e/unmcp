"""Configuration loading and management."""

import json
from pathlib import Path

from mcp2cli.models import Mcp2CliConfig, Mcp2CliSettings

# Base directory
MCP2CLI_DIR = Path(".mcp2cli")

# File and directory names within .mcp2cli/
MCP_CONFIG_PATH = MCP2CLI_DIR / ".mcp.json"
SETTINGS_FILE = ".settings.json"
SERVERS_DIR = "servers"

# Temporary/runtime files under .tmp/
TMP_DIR = ".tmp"
PROCESSES_DIR = ".tmp/processes"
SOCKETS_DIR = ".tmp/sockets"
LOGS_DIR = ".tmp/logs"

DEFAULT_SETTINGS_PATHS = [
    MCP2CLI_DIR / SETTINGS_FILE,
    Path.home() / ".mcp2cli" / SETTINGS_FILE,
]


def find_mcp_config_file() -> Path | None:
    """Find the MCP config file if it exists."""
    if MCP_CONFIG_PATH.exists():
        return MCP_CONFIG_PATH
    return None


def find_settings_file() -> Path | None:
    """Find the first existing settings file."""
    for path in DEFAULT_SETTINGS_PATHS:
        if path.exists():
            return path
    return None


def load_mcp_config(path: Path | None = None) -> Mcp2CliConfig:
    """Load MCP configuration from file.

    Args:
        path: Path to config file. If None, searches default locations.

    Returns:
        Loaded configuration.

    Raises:
        FileNotFoundError: If no config file is found.
    """
    if path is None:
        path = find_mcp_config_file()

    if path is None or not path.exists():
        msg = "No configuration file found"
        raise FileNotFoundError(msg)

    with path.open() as f:
        data = json.load(f)

    return Mcp2CliConfig.model_validate(data)


def load_settings(path: Path | None = None) -> Mcp2CliSettings:
    """Load mcp2cli settings from file.

    Args:
        path: Path to settings file. If None, searches default locations.

    Returns:
        Loaded settings, or defaults if no file found.
    """
    if path is None:
        path = find_settings_file()

    if path is None or not path.exists():
        return Mcp2CliSettings()

    with path.open() as f:
        data = json.load(f)

    return Mcp2CliSettings.model_validate(data)


def get_mcp2cli_dir() -> Path:
    """Get the .mcp2cli directory, creating it if needed."""
    MCP2CLI_DIR.mkdir(exist_ok=True)
    return MCP2CLI_DIR


def get_sockets_dir() -> Path:
    """Get the sockets directory, creating it if needed."""
    sockets_dir = get_mcp2cli_dir() / SOCKETS_DIR
    sockets_dir.mkdir(parents=True, exist_ok=True)
    return sockets_dir


def get_socket_path(server_name: str) -> Path:
    """Get the socket path for a server."""
    return get_sockets_dir() / f"{server_name}.sock"


def get_servers_dir() -> Path:
    """Get the servers cache directory, creating it if needed."""
    servers_dir = get_mcp2cli_dir() / SERVERS_DIR
    servers_dir.mkdir(exist_ok=True)
    return servers_dir


def get_tools_cache_path(server_name: str) -> Path:
    """Get path to the tools cache file for a server."""
    return get_servers_dir() / f"{server_name}.json"
