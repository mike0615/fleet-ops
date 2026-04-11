"""DHCP Manager Tool"""
from backend.tools.base import Tool

class DHCPTool(Tool):
    def __init__(self):
        super().__init__(
            name="dhcp",
            icon="network-wired",
            description="DHCP server configuration and management"
        )

    @property
    def display_name(self) -> str:
        return "DHCP Manager"

    def get_permissions(self):
        return [{"resource": "dhcp", "action": "manage"}]

    def register_routes(self, app):
        pass

def get_tool():
    return DHCPTool()
