"""Configuration loading and management."""

import json
from pathlib import Path

from nomcp.models import NoMCPConfig

DEFAULT_CONFIG_PATHS = [
    Path(".nomcp") / "config.json",
    Path.home() / ".nomcp" / "config.json",
]


def find_config_file() -> Path | None:
    """Find the first existing config file."""
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    return None


def load_config(path: Path | None = None) -> NoMCPConfig:
    """Load configuration from file.

    Args:
        path: Path to config file. If None, searches default locations.

    Returns:
        Loaded configuration.

    Raises:
        FileNotFoundError: If no config file is found.
    """
    if path is None:
        path = find_config_file()

    if path is None or not path.exists():
        msg = "No configuration file found"
        raise FileNotFoundError(msg)

    with path.open() as f:
        data = json.load(f)

    return NoMCPConfig.model_validate(data)


def get_nomcp_dir() -> Path:
    """Get the .nomcp directory, creating it if needed."""
    nomcp_dir = Path(".nomcp")
    nomcp_dir.mkdir(exist_ok=True)
    return nomcp_dir
