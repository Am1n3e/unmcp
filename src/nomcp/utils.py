"""Utility functions for noMCP."""

import json
import re
import shutil
import subprocess

from nomcp.config import get_tools_cache_path
from nomcp.models import ToolsCache


def _extract_package_name(args: list[str]) -> str | None:
    """Extract npm package name from command args.

    Handles formats like:
    - @playwright/mcp@latest -> @playwright/mcp
    - @playwright/mcp@0.0.56 -> @playwright/mcp
    - @playwright/mcp -> @playwright/mcp
    """
    for arg in args:
        # Match scoped packages (@org/pkg) or regular packages
        match = re.match(r"^(@?[^@]+)(?:@.*)?$", arg)
        if match:
            pkg = match.group(1)
            # Check if it looks like a package name
            if "/" in pkg or not pkg.startswith("-"):
                return pkg
    return None


def _extract_version_from_args(args: list[str]) -> str | None:
    """Extract version specifier from command args.

    Handles formats like:
    - @playwright/mcp@latest -> latest
    - @playwright/mcp@0.0.56 -> 0.0.56
    - @playwright/mcp -> None
    """
    for arg in args:
        if "@" in arg:
            # Handle scoped packages (@org/pkg@version)
            parts = arg.rsplit("@", 1)
            if (
                len(parts) == 2
                and parts[1]
                and ("/" in parts[0] or not parts[0].startswith("@"))
            ):
                return parts[1]
    return None


def get_package_version(command: str, args: list[str]) -> str | None:
    """Get the version of an npm package.

    Tries npm view first, falls back to parsing args.

    Args:
        command: The command (e.g., "npx")
        args: Command arguments

    Returns:
        Version string or None if not determinable.
    """
    # Only handle npx commands
    if command not in ("npx", "npx.cmd"):
        return None

    package_name = _extract_package_name(args)
    if not package_name:
        return None

    # Try npm view if npm is available
    npm_path = shutil.which("npm")
    if npm_path:
        try:
            result = subprocess.run(  # noqa: S603
                [npm_path, "view", package_name, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                if version:
                    return version
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fall back to parsing from args
    return _extract_version_from_args(args)


def load_tools_cache(server_name: str) -> ToolsCache | None:
    """Load cached tools for a server."""
    path = get_tools_cache_path(server_name)
    if not path.exists():
        return None

    with path.open() as f:
        data = json.load(f)

    return ToolsCache.model_validate(data)


def save_tools_cache(cache: ToolsCache) -> None:
    """Save tools cache to disk."""
    path = get_tools_cache_path(cache.server_name)
    with path.open("w") as f:
        json.dump(cache.model_dump(mode="json"), f, indent=2)
