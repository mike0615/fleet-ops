"""
Maytag Admin Console (MAC) Tools Framework.
Provides a pluggable architecture for adding new administration tools.
"""

from .base import Tool, ToolRegistry, tool_registry
from .loader import load_tools, initialize_tools, shutdown_tools, get_available_tools

__all__ = [
    "Tool",
    "ToolRegistry",
    "tool_registry",
    "load_tools",
    "initialize_tools",
    "shutdown_tools",
    "get_available_tools",
]
