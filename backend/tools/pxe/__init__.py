"""PXE Boot Management Tool (LRN-PXE Integration)"""
from backend.tools.base import Tool

class PXETool(Tool):
    def __init__(self):
        super().__init__(
            name="pxe",
            icon="network-wired",
            description="PXE boot management and LRN-PXE integration"
        )

    @property
    def display_name(self) -> str:
        return "PXE Boot"

    def get_permissions(self):
        return [{"resource": "pxe", "action": "manage"}]

    def register_routes(self, app):
        pass

def get_tool():
    return PXETool()
