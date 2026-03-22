#!/usr/bin/env python3
"""
LRN_PXE Development Runner (Windows-compatible)
Sets up mock data directories and starts Flask for local preview.
"""
import os, sys, tempfile

# Use a temp directory for dev data
DEV_DIR = os.path.join(tempfile.gettempdir(), "lrn_pxe_dev")
os.environ.setdefault("LRN_PXE_DIR", DEV_DIR)
os.environ.setdefault("LRN_PXE_PORT", "8080")

# Create mock data dirs + seed data
import json
for d in ["isos", "kickstarts", "boot", "mounts", "config", "logs"]:
    os.makedirs(os.path.join(DEV_DIR, d), exist_ok=True)

# Seed settings
settings_path = os.path.join(DEV_DIR, "config", "settings.json")
if not os.path.exists(settings_path):
    with open(settings_path, "w") as f:
        json.dump({
            "server_ip": "192.168.1.10",
            "web_port": 8080,
            "dhcp_enabled": True,
            "dhcp_interface": "eth0",
            "dhcp_start": "192.168.1.100",
            "dhcp_end": "192.168.1.200",
            "dhcp_netmask": "255.255.255.0",
            "dhcp_gateway": "192.168.1.1",
            "dhcp_dns": "192.168.1.10",
            "dhcp_lease_time": "12h",
            "version": "1.0.0"
        }, f, indent=2)

# Seed menu
menu_path = os.path.join(DEV_DIR, "config", "menu.json")
if not os.path.exists(menu_path):
    with open(menu_path, "w") as f:
        json.dump({
            "title": "LRN_PXE Boot Menu",
            "timeout": 60,
            "default": "",
            "entries": [
                {
                    "id": "rocky9-auto",
                    "iso_id": "Rocky-9.4-x86_64-dvd",
                    "label": "Rocky Linux 9.4 (Auto Install)",
                    "os_type": "rhel",
                    "kickstart": "rocky9-auto.ks",
                    "kernel_args": "",
                    "enabled": True
                },
                {
                    "id": "rocky9-manual",
                    "iso_id": "Rocky-9.4-x86_64-dvd",
                    "label": "Rocky Linux 9.4 (Interactive)",
                    "os_type": "rhel",
                    "kickstart": "",
                    "kernel_args": "",
                    "enabled": True
                }
            ]
        }, f, indent=2)

# Seed mock ISO metadata (no actual file needed for UI preview)
mock_iso = os.path.join(DEV_DIR, "isos", "Rocky-9.4-x86_64-dvd.iso.info")
if not os.path.exists(mock_iso):
    with open(mock_iso, "w") as f:
        f.write("mock")

# Seed mock kickstart
ks_path = os.path.join(DEV_DIR, "kickstarts", "rocky9-auto.ks")
if not os.path.exists(ks_path):
    with open(ks_path, "w") as f:
        f.write("# Rocky Linux 9 Auto Kickstart\ntext\nlang en_US.UTF-8\n")

# Mock boot dir
boot_dir = os.path.join(DEV_DIR, "boot", "Rocky-9.4-x86_64-dvd")
os.makedirs(boot_dir, exist_ok=True)
for fname in ["vmlinuz", "initrd.img"]:
    p = os.path.join(boot_dir, fname)
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write("mock")

sys.path.insert(0, os.path.dirname(__file__))

# Patch service_status to return mock data on Windows
import app as flask_app
flask_app.service_status = lambda name: "active"

# Patch list_isos to return mock data
def mock_list_isos():
    return [
        {
            "id": "Rocky-9.4-x86_64-dvd",
            "filename": "Rocky-9.4-x86_64-dvd.iso",
            "size": "9.4 GB",
            "size_bytes": 10_000_000_000,
            "modified": "2024-06-01 12:00",
            "has_boot": True,
            "mounted": True
        }
    ]
flask_app.list_isos = mock_list_isos

print(f"\n  LRN_PXE Dev Server")
print(f"  -------------------------------------")
print(f"  Data dir : {DEV_DIR}")
print(f"  URL      : http://localhost:8080/\n")

flask_app.app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
