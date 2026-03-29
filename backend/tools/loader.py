"""
Tool loader and manager for Maytag Admin Console.
Dynamically loads tools from the tools directory.
"""

import importlib
import logging
from pathlib import Path
from typing import List

from .base import tool_registry, Tool

logger = logging.getLogger(__name__)


def load_tools(tools_dir: Path = None) -> None:
    """
    Discover and load all tools from the tools directory.

    Args:
        tools_dir: Path to tools directory. Defaults to this directory.
    """
    if tools_dir is None:
        tools_dir = Path(__file__).parent

    logger.info(f"Loading tools from {tools_dir}")

    # Skip the base modules
    skip_dirs = {"__pycache__", ".git"}
    skip_files = {"__init__.py", "base.py", "loader.py"}

    # Iterate through subdirectories
    for item in tools_dir.iterdir():
        if item.is_dir() and item.name not in skip_dirs:
            tool_name = item.name
            init_file = item / "__init__.py"

            if init_file.exists():
                try:
                    # Dynamically import the tool module
                    module_path = f"backend.tools.{tool_name}"
                    module = importlib.import_module(module_path)

                    # Look for a get_tool() function or Tool subclass
                    if hasattr(module, "get_tool"):
                        tool = module.get_tool()
                        tool_registry.register(tool)
                        logger.info(f"✓ Loaded tool: {tool_name} ({tool.display_name})")
                    else:
                        logger.warning(
                            f"Tool module {tool_name} has no get_tool() function"
                        )

                except Exception as e:
                    logger.error(f"✗ Failed to load tool {tool_name}: {e}")


def initialize_tools(app) -> None:
    """
    Initialize all registered tools with the Flask app.

    Args:
        app: Flask application instance
    """
    for tool_name, tool in tool_registry.get_all().items():
        try:
            logger.info(f"Initializing tool: {tool_name}")
            tool.initialize(app)
            tool.register_routes(app)
            logger.info(f"✓ Initialized tool: {tool_name}")
        except Exception as e:
            logger.error(f"✗ Failed to initialize tool {tool_name}: {e}")


def shutdown_tools() -> None:
    """Shutdown all tools."""
    for tool_name, tool in tool_registry.get_all().items():
        try:
            logger.info(f"Shutting down tool: {tool_name}")
            tool.shutdown()
        except Exception as e:
            logger.error(f"✗ Failed to shutdown tool {tool_name}: {e}")


def get_available_tools(user_permissions: List[str] = None) -> List[dict]:
    """
    Get list of available tools for a user based on permissions.

    Args:
        user_permissions: List of user's permissions

    Returns:
        List of tool info dicts with name, display_name, icon, description
    """
    if user_permissions is None:
        user_permissions = []

    available = []
    for tool_name, tool in tool_registry.get_all().items():
        # Check if user has permissions for this tool
        tool_perms = tool.get_permissions()
        has_access = True

        if tool_perms and user_permissions:
            # At least one permission is required
            has_access = any(
                f"{perm['resource']}:{perm['action']}" in user_permissions
                for perm in tool_perms
            )

        if has_access:
            available.append(
                {
                    "name": tool_name,
                    "display_name": tool.display_name,
                    "icon": tool.icon,
                    "description": tool.description,
                }
            )

    return available
