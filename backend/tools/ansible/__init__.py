"""
Ansible Tool for FleetOps.
Provides web UI for managing Ansible playbooks and automation.
"""

from typing import List, Dict, Any
from backend.tools.base import Tool


class AnsibleTool(Tool):
    """Ansible automation tool."""

    def __init__(self):
        super().__init__(
            name="ansible",
            icon="robot",
            description="Manage Ansible playbooks, inventory, and automation tasks",
        )

    @property
    def display_name(self) -> str:
        return "Ansible"

    def get_permissions(self) -> List[Dict[str, str]]:
        return [
            {"resource": "ansible", "action": "view_playbooks"},
            {"resource": "ansible", "action": "execute_playbook"},
            {"resource": "ansible", "action": "view_inventory"},
            {"resource": "ansible", "action": "edit_inventory"},
            {"resource": "ansible", "action": "view_ssh"},
            {"resource": "ansible", "action": "access_terminal"},
        ]

    def register_routes(self, app) -> None:
        """Register Ansible routes with Flask app."""
        # Routes will be registered here
        # For now, this is a placeholder
        pass

    def initialize(self, app) -> None:
        """Initialize Ansible tool."""
        pass


def get_tool() -> Tool:
    """Factory function to get the Ansible tool."""
    return AnsibleTool()
