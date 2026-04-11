"""DNS Manager Tool (Bind)"""
from backend.tools.base import Tool

class DNSTool(Tool):
    def __init__(self):
        super().__init__(
            name="dns",
            icon="globe",
            description="Bind DNS server configuration and management"
        )

    @property
    def display_name(self) -> str:
        return "DNS Manager"

    def get_permissions(self):
        return [{"resource": "dns", "action": "manage"}]

    def register_routes(self, app):
        pass

def get_tool():
    return DNSTool()
