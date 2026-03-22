#!/usr/bin/env python3
"""
LRN_PXE - Web Management Interface
Flask application for managing PXE boot images, kickstarts, and menus.
"""

import os
import re
import json
import shutil
import hashlib
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, abort, Response, stream_with_context
)

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR    = os.environ.get("LRN_PXE_DIR", "/opt/lrn_pxe")
PORT        = int(os.environ.get("LRN_PXE_PORT", 8080))
ISOS_DIR    = os.path.join(BASE_DIR, "isos")
KS_DIR      = os.path.join(BASE_DIR, "kickstarts")
BOOT_DIR    = os.path.join(BASE_DIR, "boot")
MOUNTS_DIR  = os.path.join(BASE_DIR, "mounts")
CONFIG_DIR  = os.path.join(BASE_DIR, "config")
MENU_JSON   = os.path.join(CONFIG_DIR, "menu.json")
SETTINGS_JSON = os.path.join(CONFIG_DIR, "settings.json")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024 * 1024  # 50 GB

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_settings():
    return load_json(SETTINGS_JSON, {
        "server_ip": "127.0.0.1",
        "web_port": PORT,
        "dhcp_enabled": True,
    })

def get_menu():
    return load_json(MENU_JSON, {
        "title": "LRN_PXE Boot Menu",
        "timeout": 60,
        "default": "",
        "entries": []
    })

def human_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def slugify(name):
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_-]+", "-", name).strip("-")

def service_status(name):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"

def disk_info():
    try:
        stat = shutil.disk_usage(BASE_DIR)
        return {
            "total": human_size(stat.total),
            "used":  human_size(stat.used),
            "free":  human_size(stat.free),
            "pct":   round(stat.used / stat.total * 100, 1)
        }
    except Exception:
        return {"total": "N/A", "used": "N/A", "free": "N/A", "pct": 0}

def list_isos():
    entries = []
    for f in sorted(Path(ISOS_DIR).glob("*.iso")):
        stat = f.stat()
        entries.append({
            "id":       f.stem,
            "filename": f.name,
            "size":     human_size(stat.st_size),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "has_boot": Path(BOOT_DIR, f.stem).exists(),
            "mounted":  Path(MOUNTS_DIR, f.stem).is_mount() or
                        bool(list(Path(MOUNTS_DIR, f.stem).glob("*")) if Path(MOUNTS_DIR, f.stem).exists() else [])
        })
    return entries

def list_kickstarts():
    entries = []
    for f in sorted(Path(KS_DIR).iterdir()) if Path(KS_DIR).exists() else []:
        if f.suffix in (".ks", ".cfg", ".txt"):
            stat = f.stat()
            entries.append({
                "name":     f.name,
                "size":     human_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return entries

# ── iPXE Menu generator ───────────────────────────────────────────────────────
def generate_ipxe_menu():
    settings = get_settings()
    menu     = get_menu()
    server   = settings.get("server_ip", "127.0.0.1")
    port     = settings.get("web_port", PORT)
    base_url = f"http://{server}:{port}"
    # nginx serves on 80 and proxies; use port 80 for boot files
    file_url = f"http://{server}"

    lines = ["#!ipxe", ""]
    lines.append(f"set base_url {base_url}")
    lines.append(f"set file_url {file_url}")
    lines.append("")

    # Menu header
    title = menu.get("title", "LRN_PXE Boot Menu")
    timeout = menu.get("timeout", 60)
    default = menu.get("default", "")

    lines.append(f"menu {title}")
    lines.append("item --gap --  ────────────── Boot Images ──────────────")

    entries = [e for e in menu.get("entries", []) if e.get("enabled", True)]

    if not entries:
        lines.append("item --gap --  (No boot images configured)")
        lines.append("item --gap --  Add images at the web interface")
    else:
        for entry in entries:
            eid   = entry.get("id", "")
            label = entry.get("label", eid)
            has_ks = bool(entry.get("kickstart"))
            ks_tag = "  [Auto Install]" if has_ks else "  [Interactive]"
            lines.append(f"item {eid}  {label}{ks_tag}")

    lines.append("item --gap --")
    lines.append("item --gap --  ────────────── Utilities ──────────────")
    lines.append("item --key s shell   iPXE Shell")
    lines.append("item --key r reboot  Reboot System")
    lines.append("item --key x exit    Exit to BIOS/UEFI")
    lines.append("")

    if default:
        lines.append(f"choose --timeout {timeout * 1000} --default {default} target && goto ${{target}}")
    else:
        lines.append(f"choose --timeout {timeout * 1000} target && goto ${{target}}")

    lines.append("goto menu")
    lines.append("")

    # Boot stanzas
    for entry in entries:
        eid        = entry.get("id", "")
        iso_id     = entry.get("iso_id", eid)
        ks_file    = entry.get("kickstart", "")
        kernel_args = entry.get("kernel_args", "")
        os_type    = entry.get("os_type", "rhel")

        lines.append(f":{eid}")

        if os_type in ("rhel", "rocky", "centos", "fedora", "almalinux"):
            ks_param = f" inst.ks={file_url}/kickstarts/{ks_file}" if ks_file else ""
            lines.append(f"kernel {file_url}/boot/{iso_id}/vmlinuz inst.repo={file_url}/mounts/{iso_id}/ inst.text{ks_param} {kernel_args}")
            lines.append(f"initrd {file_url}/boot/{iso_id}/initrd.img")
        elif os_type in ("ubuntu", "debian"):
            ks_param = f" ks={file_url}/kickstarts/{ks_file}" if ks_file else ""
            lines.append(f"kernel {file_url}/boot/{iso_id}/vmlinuz auto=true url={file_url}/kickstarts/{ks_file} {kernel_args}" if ks_file
                         else f"kernel {file_url}/boot/{iso_id}/vmlinuz {kernel_args}")
            lines.append(f"initrd {file_url}/boot/{iso_id}/initrd")
        else:
            lines.append(f"kernel {file_url}/boot/{iso_id}/vmlinuz {kernel_args}")
            lines.append(f"initrd {file_url}/boot/{iso_id}/initrd.img")

        lines.append("boot")
        lines.append("")

    lines += [":shell", "shell", "", ":reboot", "reboot", "", ":exit", "exit", ":menu", "goto menu"]

    return "\n".join(lines)

# ── Extract boot files from ISO ───────────────────────────────────────────────
EXTRACT_STATUS = {}  # iso_id -> {status, message, progress}

def _detect_os_type(mount_path):
    """Detect OS type from mounted ISO."""
    p = Path(mount_path)
    if (p / ".discinfo").exists() or (p / "BaseOS").exists():
        return "rhel"
    if (p / ".disk").exists() or (p / "casper").exists():
        return "ubuntu"
    if (p / "debian").exists():
        return "debian"
    return "rhel"

def _find_boot_files(mount_path, os_type):
    """Return (vmlinuz_path, initrd_path) from mounted ISO."""
    p = Path(mount_path)
    candidates = {
        "rhel": [
            ("images/pxeboot/vmlinuz", "images/pxeboot/initrd.img"),
            ("isolinux/vmlinuz",       "isolinux/initrd.img"),
        ],
        "ubuntu": [
            ("casper/vmlinuz",         "casper/initrd"),
            ("install/vmlinuz",        "install/initrd.gz"),
        ],
        "debian": [
            ("install.amd/vmlinuz",    "install.amd/initrd.gz"),
            ("install/vmlinuz",        "install/initrd.gz"),
        ],
    }
    for vmlinuz_rel, initrd_rel in candidates.get(os_type, candidates["rhel"]):
        vmlinuz = p / vmlinuz_rel
        initrd  = p / initrd_rel
        if vmlinuz.exists() and initrd.exists():
            return str(vmlinuz), str(initrd)
    return None, None

def _do_extract(iso_id, iso_path):
    """Run extraction in a background thread."""
    EXTRACT_STATUS[iso_id] = {"status": "running", "message": "Mounting ISO...", "progress": 10}

    mount_path = os.path.join(MOUNTS_DIR, iso_id)
    boot_path  = os.path.join(BOOT_DIR,   iso_id)
    os.makedirs(mount_path, exist_ok=True)
    os.makedirs(boot_path,  exist_ok=True)

    try:
        # Mount ISO
        result = subprocess.run(
            ["mount", "-o", "loop,ro", iso_path, mount_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            # Try without kernel module (copy approach)
            EXTRACT_STATUS[iso_id]["message"] = "Extracting ISO contents..."
            subprocess.run(["cp", "-r", "--no-preserve=ownership", iso_path, mount_path + "/"],
                           check=False)

        EXTRACT_STATUS[iso_id] = {"status": "running", "message": "Detecting OS type...", "progress": 40}

        os_type = _detect_os_type(mount_path)
        vmlinuz, initrd = _find_boot_files(mount_path, os_type)

        if not vmlinuz:
            raise RuntimeError("Could not find vmlinuz/initrd in ISO. The ISO may not support network booting.")

        EXTRACT_STATUS[iso_id] = {"status": "running", "message": "Copying boot files...", "progress": 70}

        shutil.copy2(vmlinuz, os.path.join(boot_path, "vmlinuz"))
        shutil.copy2(initrd,  os.path.join(boot_path, os.path.basename(initrd)))
        # Normalize initrd filename
        for name in os.listdir(boot_path):
            if name.startswith("initrd"):
                target = "initrd.img" if os_type == "rhel" else "initrd"
                os.rename(os.path.join(boot_path, name), os.path.join(boot_path, target))
                break

        # Update menu entry os_type if entry exists
        menu = get_menu()
        for entry in menu.get("entries", []):
            if entry.get("iso_id") == iso_id:
                entry["os_type"] = os_type
        save_json(MENU_JSON, menu)

        EXTRACT_STATUS[iso_id] = {"status": "done", "message": f"Boot files extracted ({os_type})", "progress": 100}

    except Exception as e:
        # Cleanup on failure
        try:
            subprocess.run(["umount", "-f", mount_path], capture_output=True)
        except Exception:
            pass
        EXTRACT_STATUS[iso_id] = {"status": "error", "message": str(e), "progress": 0}

# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTES — Pages
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    settings = get_settings()
    menu     = get_menu()
    isos     = list_isos()
    ks_list  = list_kickstarts()
    return render_template("dashboard.html",
        settings=settings, menu=menu,
        iso_count=len(isos), ks_count=len(ks_list),
        menu_count=len(menu.get("entries", [])),
        services={
            "lrn-pxe":  service_status("lrn-pxe"),
            "dnsmasq":  service_status("dnsmasq"),
            "nginx":    service_status("nginx"),
        },
        disk=disk_info(),
    )

@app.route("/images")
def images_page():
    settings = get_settings()
    isos = list_isos()
    menu = get_menu()
    # Find which isos are already in the menu
    menu_isos = {e.get("iso_id") for e in menu.get("entries", [])}
    return render_template("images.html", settings=settings, isos=isos, menu_isos=menu_isos)

@app.route("/kickstarts")
def kickstarts_page():
    settings = get_settings()
    ks_list = list_kickstarts()
    return render_template("kickstarts.html", settings=settings, ks_list=ks_list)

@app.route("/menu-builder")
def menu_builder_page():
    settings = get_settings()
    menu     = get_menu()
    isos     = list_isos()
    ks_list  = list_kickstarts()
    return render_template("menu_builder.html",
        settings=settings, menu=menu, isos=isos, ks_list=ks_list)

@app.route("/settings")
def settings_page():
    settings = get_settings()
    return render_template("settings.html", settings=settings)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTES — iPXE Menu (served to booting clients)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/menu.ipxe")
def ipxe_menu():
    script = generate_ipxe_menu()
    return Response(script, mimetype="text/plain")

# ═══════════════════════════════════════════════════════════════════════════════
#  API — Images
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/images", methods=["GET"])
def api_images_list():
    return jsonify(list_isos())

@app.route("/api/images/upload", methods=["POST"])
def api_images_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".iso"):
        return jsonify({"error": "Only .iso files are supported"}), 400

    filename = file.filename
    dest = os.path.join(ISOS_DIR, filename)
    file.save(dest)

    iso_id = Path(filename).stem
    # Auto-add to menu if not already there
    menu = get_menu()
    existing_ids = [e.get("id") for e in menu.get("entries", [])]
    if iso_id not in existing_ids:
        menu["entries"].append({
            "id":       slugify(iso_id),
            "iso_id":   iso_id,
            "label":    iso_id,
            "os_type":  "rhel",
            "kickstart": "",
            "kernel_args": "",
            "enabled":  False,  # disabled until boot files are extracted
        })
        save_json(MENU_JSON, menu)

    return jsonify({"success": True, "filename": filename, "iso_id": iso_id})

@app.route("/api/images/<iso_id>", methods=["DELETE"])
def api_images_delete(iso_id):
    # Remove ISO file
    for f in Path(ISOS_DIR).glob(f"{iso_id}.*"):
        f.unlink(missing_ok=True)
    # Remove boot files
    boot_path = Path(BOOT_DIR) / iso_id
    if boot_path.exists():
        shutil.rmtree(boot_path, ignore_errors=True)
    # Unmount and remove mount
    mount_path = Path(MOUNTS_DIR) / iso_id
    if mount_path.is_mount():
        subprocess.run(["umount", "-f", str(mount_path)], capture_output=True)
    if mount_path.exists():
        shutil.rmtree(mount_path, ignore_errors=True)
    # Remove from menu
    menu = get_menu()
    menu["entries"] = [e for e in menu.get("entries", []) if e.get("iso_id") != iso_id]
    save_json(MENU_JSON, menu)
    return jsonify({"success": True})

@app.route("/api/images/<iso_id>/extract", methods=["POST"])
def api_images_extract(iso_id):
    iso_path = os.path.join(ISOS_DIR, f"{iso_id}.iso")
    if not os.path.exists(iso_path):
        return jsonify({"error": f"ISO file not found: {iso_id}.iso"}), 404

    EXTRACT_STATUS[iso_id] = {"status": "pending", "message": "Queued", "progress": 0}
    t = threading.Thread(target=_do_extract, args=(iso_id, iso_path), daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Extraction started"})

@app.route("/api/images/<iso_id>/extract/status", methods=["GET"])
def api_images_extract_status(iso_id):
    status = EXTRACT_STATUS.get(iso_id, {"status": "unknown", "message": "No job found", "progress": 0})
    # If done, enable the menu entry
    if status.get("status") == "done":
        menu = get_menu()
        for entry in menu.get("entries", []):
            if entry.get("iso_id") == iso_id:
                entry["enabled"] = True
        save_json(MENU_JSON, menu)
    return jsonify(status)

# ═══════════════════════════════════════════════════════════════════════════════
#  API — Kickstarts
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/kickstarts", methods=["GET"])
def api_ks_list():
    return jsonify(list_kickstarts())

@app.route("/api/kickstarts/upload", methods=["POST"])
def api_ks_upload():
    if "file" in request.files:
        file = request.files["file"]
        dest = os.path.join(KS_DIR, file.filename)
        file.save(dest)
        return jsonify({"success": True, "name": file.filename})
    elif request.is_json:
        data = request.get_json()
        name = data.get("name", "").strip()
        content = data.get("content", "")
        if not name:
            return jsonify({"error": "Filename required"}), 400
        if not name.endswith((".ks", ".cfg")):
            name += ".ks"
        dest = os.path.join(KS_DIR, name)
        with open(dest, "w") as f:
            f.write(content)
        return jsonify({"success": True, "name": name})
    return jsonify({"error": "No file or content provided"}), 400

@app.route("/api/kickstarts/<name>", methods=["GET"])
def api_ks_read(name):
    path = os.path.join(KS_DIR, name)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    with open(path) as f:
        content = f.read()
    return jsonify({"name": name, "content": content})

@app.route("/api/kickstarts/<name>", methods=["PUT"])
def api_ks_update(name):
    data = request.get_json()
    path = os.path.join(KS_DIR, name)
    with open(path, "w") as f:
        f.write(data.get("content", ""))
    return jsonify({"success": True})

@app.route("/api/kickstarts/<name>", methods=["DELETE"])
def api_ks_delete(name):
    path = os.path.join(KS_DIR, name)
    if os.path.exists(path):
        os.unlink(path)
    return jsonify({"success": True})

# ═══════════════════════════════════════════════════════════════════════════════
#  API — Menu
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/menu", methods=["GET"])
def api_menu_get():
    return jsonify(get_menu())

@app.route("/api/menu", methods=["PUT"])
def api_menu_save():
    data = request.get_json()
    save_json(MENU_JSON, data)
    return jsonify({"success": True})

@app.route("/api/menu/entries", methods=["POST"])
def api_menu_add_entry():
    data = request.get_json()
    menu = get_menu()
    # Check for duplicate ID
    existing = [e.get("id") for e in menu.get("entries", [])]
    eid = data.get("id", slugify(data.get("label", "entry")))
    if eid in existing:
        eid = eid + "-2"
    data["id"] = eid
    menu["entries"].append(data)
    save_json(MENU_JSON, menu)
    return jsonify({"success": True, "id": eid})

@app.route("/api/menu/entries/<entry_id>", methods=["PUT"])
def api_menu_update_entry(entry_id):
    data = request.get_json()
    menu = get_menu()
    for i, entry in enumerate(menu.get("entries", [])):
        if entry.get("id") == entry_id:
            menu["entries"][i].update(data)
            break
    save_json(MENU_JSON, menu)
    return jsonify({"success": True})

@app.route("/api/menu/entries/<entry_id>", methods=["DELETE"])
def api_menu_delete_entry(entry_id):
    menu = get_menu()
    menu["entries"] = [e for e in menu.get("entries", []) if e.get("id") != entry_id]
    save_json(MENU_JSON, menu)
    return jsonify({"success": True})

@app.route("/api/menu/reorder", methods=["POST"])
def api_menu_reorder():
    order = request.get_json()  # list of ids in new order
    menu = get_menu()
    id_to_entry = {e.get("id"): e for e in menu.get("entries", [])}
    menu["entries"] = [id_to_entry[i] for i in order if i in id_to_entry]
    save_json(MENU_JSON, menu)
    return jsonify({"success": True})

# ═══════════════════════════════════════════════════════════════════════════════
#  API — Settings
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify(get_settings())

@app.route("/api/settings", methods=["PUT"])
def api_settings_save():
    data = request.get_json()
    save_json(SETTINGS_JSON, data)
    return jsonify({"success": True})

# ═══════════════════════════════════════════════════════════════════════════════
#  API — Status
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "services": {
            "lrn-pxe":  service_status("lrn-pxe"),
            "dnsmasq":  service_status("dnsmasq"),
            "nginx":    service_status("nginx"),
        },
        "disk": disk_info(),
        "iso_count": len(list_isos()),
        "ks_count":  len(list_kickstarts()),
        "menu_entries": len(get_menu().get("entries", [])),
    })

@app.route("/api/service/<name>/restart", methods=["POST"])
def api_service_restart(name):
    allowed = {"dnsmasq", "nginx", "lrn-pxe"}
    if name not in allowed:
        return jsonify({"error": "Not allowed"}), 403
    try:
        subprocess.run(["systemctl", "restart", name], check=True, timeout=15)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure directories exist
    for d in [ISOS_DIR, KS_DIR, BOOT_DIR, MOUNTS_DIR, CONFIG_DIR]:
        os.makedirs(d, exist_ok=True)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
