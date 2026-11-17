"""
Base class for FleetOps tools.
All tools inherit from this class to register with the tool framework.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class Tool(ABC):
    """Base class for FleetOps tools."""

    def __init__(self, name: str, icon: str = "wrench", description: str = ""):
        """
        Initialize a tool.

        Args:
            name: Tool identifier (e.g., 'ansible', 'pxe', 'dhcp')
            icon: Font Awesome icon name (e.g., 'wrench', 'network-wired')
            description: Human-readable description of the tool
        """
        self.name = name
        self.icon = icon
        self.description = description
        self.routes = []
        self.required_permissions = []

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return the display name for the tool."""
        pass

    @abstractmethod
    def register_routes(self, app) -> None:
        """
        Register Flask routes for this tool.

        Args:
            app: Flask application instance
        """
        pass

    @abstractmethod
    def get_permissions(self) -> List[Dict[str, str]]:
        """
        Return list of permissions required by this tool.

        Returns:
            List of dicts with 'resource' and 'action' keys
            Example: [{'resource': 'ansible', 'action': 'execute'}]
        """
        pass

    def get_config(self) -> Dict[str, Any]:
        """
        Return tool configuration (optional).

        Returns:
            Dictionary with tool configuration
        """
        return {}

    def initialize(self, app) -> None:
        """
        Initialize the tool with the Flask app.
        Called once on startup.

        Args:
            app: Flask application instance
        """
        pass

    def shutdown(self) -> None:
        """
        Shutdown hook for cleanup.
        Called on application shutdown.
        """
        pass


class ToolRegistry:
    """Registry for managing all FleetOps tools."""

    def __init__(self):
        """Initialize the tool registry."""
        self.tools = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self.tools.get(name)

    def get_all(self) -> Dict[str, Tool]:
        """
        Get all registered tools.

        Returns:
            Dictionary of tool_name -> Tool instance
        """
        return self.tools.copy()

    def unregister(self, name: str) -> None:
        """
        Unregister a tool.

        Args:
            name: Tool name
        """
        if name in self.tools:
            del self.tools[name]


# Global tool registry
tool_registry = ToolRegistry()
