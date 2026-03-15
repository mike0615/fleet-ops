#!/usr/bin/env python3
"""
=============================================================================
mac-ops — Maytag Ansible Console Backend
=============================================================================
Author  : Mike Anderson
Version : 1.1.0
License : MIT

Flask REST API providing:
  - Playbook CRUD + execution
  - Inventory CRUD
  - File browser (playbooks & inventory directories)
  - Schedule management (cron via APScheduler)
  - Report viewer
  - Execution log viewer
  - Dashboard statistics

Designed for airgapped Rocky Linux 9.7 deployment.
No external network calls are made at runtime.
=============================================================================
"""

import os
import sys
import json
import glob
import uuid
import time
import subprocess
import datetime
import logging
import yaml
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ─── Path layout ─────────────────────────────────────────────────────────────
BASE        = Path(__file__).resolve().parent.parent
FRONTEND    = BASE / "frontend"
PLAYBOOKS   = BASE / "ansible" / "playbooks"
INVENTORY   = BASE / "ansible" / "inventory"
REPORTS     = BASE / "reports"
LOGS        = BASE / "logs"
SCHED_FILE  = BASE / "backend" / "schedules.json"

for _d in [PLAYBOOKS, INVENTORY, REPORTS, LOGS]:
    _d.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS / "mac-ops.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mac-ops")
log.info("mac-ops v1.1.0 starting — Author: Mike Anderson")

# ─── App ──────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
CORS(app)

# ─── Scheduler ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

# ─── Helpers ─────────────────────────────────────────────────────────────────
def load_schedules() -> list:
    if SCHED_FILE.exists():
        try:
            return json.loads(SCHED_FILE.read_text())
        except Exception:
            return []
    return []


def save_schedules(data: list) -> None:
    SCHED_FILE.write_text(json.dumps(data, indent=2))


def fmtime(p: Path) -> str:
    return datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat()


def run_playbook(playbook: Path, inventory: Path,
                 extra_vars: dict = None, run_id: str = None) -> dict:
    """Execute ansible-playbook as subprocess; capture output to log file."""
    run_id  = run_id or str(uuid.uuid4())[:8]
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = LOGS / f"run_{run_id}_{ts}.log"

    cmd = ["ansible-playbook", str(playbook), "-i", str(inventory), "-v"]
    if extra_vars:
        cmd += ["--extra-vars", json.dumps(extra_vars)]

    log.info("Executing: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        logfile.write_text(result.stdout + "\n" + result.stderr)
        return {
            "success":    result.returncode == 0,
            "returncode": result.returncode,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
            "log_file":   str(logfile),
            "run_id":     run_id,
        }
    except subprocess.TimeoutExpired:
        msg = "Playbook timed out after 900 seconds"
        log.error(msg)
        return {"success": False, "error": msg, "run_id": run_id}
    except Exception as exc:
        log.exception("Playbook execution failed")
        return {"success": False, "error": str(exc), "run_id": run_id}


def register_schedule(s: dict) -> None:
    try:
        parts   = s["cron"].split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4],
        )
        pb  = PLAYBOOKS / s["playbook"]
        inv = INVENTORY  / s.get("inventory", "hosts.ini")
        scheduler.add_job(
            func=lambda: run_playbook(pb, inv),
            trigger=trigger,
            id=s["id"],
            replace_existing=True,
        )
        log.info("Schedule registered: %s (%s)", s["name"], s["cron"])
    except Exception:
        log.exception("Failed to register schedule %s", s.get("id"))


# ─── Static / index ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(FRONTEND), "index.html")


@app.route("/vendor/codemirror/<path:filename>")
def vendor_codemirror(filename):
    """Serve locally bundled CodeMirror assets (airgap-safe)."""
    vendor_dir = FRONTEND / "vendor" / "codemirror"
    return send_from_directory(str(vendor_dir), filename)


# ─── Dashboard ────────────────────────────────────────────────────────────────
@app.route("/api/dashboard")
def dashboard():
    run_logs  = sorted(LOGS.glob("run_*.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    schedules = load_schedules()
    recent    = []
    for p in run_logs[:10]:
        txt    = p.read_text(errors="replace")
        status = ("success" if "PLAY RECAP" in txt and "failed=0" in txt
                  else "failed" if "PLAY RECAP" in txt else "unknown")
        recent.append({"name": p.name, "status": status, "time": fmtime(p)})
    return jsonify({
        "playbook_count":   len(list(PLAYBOOKS.rglob("*.yml")) +
                               list(PLAYBOOKS.rglob("*.yaml"))),
        "inventory_count":  len([f for f in INVENTORY.iterdir()
                                 if f.is_file()]),
        "report_count":     len(list(REPORTS.glob("*.json"))),
        "schedule_count":   len(schedules),
        "active_schedules": sum(1 for s in schedules if s.get("enabled")),
        "recent_runs":      recent,
    })


# ─── File browser ─────────────────────────────────────────────────────────────
@app.route("/api/browse/playbooks")
def browse_playbooks():
    """
    Recursive directory listing of the playbooks folder.
    Returns a tree structure: {name, path, type:'dir'|'file', children?}
    """
    def build_tree(directory: Path, rel_base: Path):
        items = []
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return items
        for entry in entries:
            rel = entry.relative_to(rel_base)
            if entry.is_dir():
                items.append({
                    "name":     entry.name,
                    "path":     str(rel),
                    "type":     "dir",
                    "children": build_tree(entry, rel_base),
                })
            elif entry.suffix in (".yml", ".yaml"):
                items.append({
                    "name":     entry.name,
                    "path":     str(rel),
                    "type":     "file",
                    "size":     entry.stat().st_size,
                    "modified": fmtime(entry),
                })
        return items

    return jsonify(build_tree(PLAYBOOKS, PLAYBOOKS))


@app.route("/api/browse/inventory")
def browse_inventory():
    """Flat listing of inventory directory (ini + yaml files)."""
    files = []
    try:
        for entry in sorted(INVENTORY.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_file():
                files.append({
                    "name":     entry.name,
                    "path":     entry.name,
                    "type":     "file",
                    "size":     entry.stat().st_size,
                    "modified": fmtime(entry),
                })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(files)


# ─── Playbooks ────────────────────────────────────────────────────────────────
@app.route("/api/playbooks")
def list_playbooks():
    files = []
    for p in sorted(list(PLAYBOOKS.rglob("*.yml")) +
                    list(PLAYBOOKS.rglob("*.yaml"))):
        rel = p.relative_to(PLAYBOOKS)
        files.append({
            "name":     str(rel),
            "path":     str(p),
            "size":     p.stat().st_size,
            "modified": fmtime(p),
        })
    return jsonify(files)


@app.route("/api/playbooks/<path:name>", methods=["GET"])
def get_playbook(name):
    p = PLAYBOOKS / name
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"name": name, "content": p.read_text(errors="replace")})


@app.route("/api/playbooks/<path:name>", methods=["PUT"])
def save_playbook(name):
    p = PLAYBOOKS / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(request.json.get("content", ""))
    log.info("Saved playbook: %s", name)
    return jsonify({"success": True})


@app.route("/api/playbooks/<path:name>", methods=["DELETE"])
def del_playbook(name):
    p = PLAYBOOKS / name
    if p.exists():
        p.unlink()
        log.info("Deleted playbook: %s", name)
    return jsonify({"success": True})


@app.route("/api/playbooks/run", methods=["POST"])
def api_run():
    d   = request.json or {}
    pb  = PLAYBOOKS / d.get("playbook", "")
    inv = INVENTORY  / d.get("inventory", "hosts.ini")
    if not pb.exists():
        return jsonify({"error": f"Playbook not found: {d.get('playbook')}"}), 404
    return jsonify(run_playbook(pb, inv, d.get("extra_vars")))


@app.route("/api/playbooks/validate", methods=["POST"])
def validate_playbook():
    content = request.json.get("content", "")
    try:
        yaml.safe_load(content)
        return jsonify({"valid": True, "message": "YAML syntax OK"})
    except yaml.YAMLError as exc:
        return jsonify({"valid": False, "message": str(exc)})


@app.route("/api/playbooks/mkdir", methods=["POST"])
def mkdir_playbook():
    """Create a sub-directory inside the playbooks folder."""
    d    = request.json or {}
    path = PLAYBOOKS / d.get("path", "")
    try:
        path.mkdir(parents=True, exist_ok=True)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ─── Inventory ────────────────────────────────────────────────────────────────
@app.route("/api/inventory")
def list_inventory():
    files = []
    for p in sorted(INVENTORY.iterdir(), key=lambda e: e.name):
        if p.is_file():
            files.append({
                "name":     p.name,
                "size":     p.stat().st_size,
                "modified": fmtime(p),
            })
    return jsonify(files)


@app.route("/api/inventory/<name>", methods=["GET"])
def get_inventory(name):
    p = INVENTORY / name
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"name": name, "content": p.read_text(errors="replace")})


@app.route("/api/inventory/<name>", methods=["PUT"])
def save_inventory(name):
    (INVENTORY / name).write_text(request.json.get("content", ""))
    log.info("Saved inventory: %s", name)
    return jsonify({"success": True})


@app.route("/api/inventory/<name>", methods=["DELETE"])
def del_inventory(name):
    p = INVENTORY / name
    if p.exists():
        p.unlink()
        log.info("Deleted inventory: %s", name)
    return jsonify({"success": True})


# ─── Schedules ────────────────────────────────────────────────────────────────
@app.route("/api/schedules")
def list_schedules():
    return jsonify(load_schedules())


@app.route("/api/schedules", methods=["POST"])
def create_schedule():
    d  = request.json or {}
    s  = {
        "id":        str(uuid.uuid4())[:8],
        "name":      d.get("name", ""),
        "playbook":  d.get("playbook", ""),
        "inventory": d.get("inventory", "hosts.ini"),
        "cron":      d.get("cron", "0 2 * * *"),
        "enabled":   True,
        "created":   datetime.datetime.now().isoformat(),
        "last_run":  None,
    }
    sl = load_schedules()
    sl.append(s)
    save_schedules(sl)
    register_schedule(s)
    return jsonify(s)


@app.route("/api/schedules/<sid>", methods=["DELETE"])
def del_schedule(sid):
    sl = [s for s in load_schedules() if s["id"] != sid]
    save_schedules(sl)
    try:
        scheduler.remove_job(sid)
    except Exception:
        pass
    return jsonify({"success": True})


@app.route("/api/schedules/<sid>/toggle", methods=["POST"])
def toggle_schedule(sid):
    sl = load_schedules()
    for s in sl:
        if s["id"] == sid:
            s["enabled"] = not s["enabled"]
            if s["enabled"]:
                register_schedule(s)
            else:
                try:
                    scheduler.remove_job(sid)
                except Exception:
                    pass
    save_schedules(sl)
    return jsonify({"success": True})


# ─── Reports ─────────────────────────────────────────────────────────────────
@app.route("/api/reports")
def list_reports():
    out = []
    for p in sorted(REPORTS.glob("*.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({
                "name":      p.name,
                "host":      d.get("host", "unknown"),
                "type":      d.get("report_type", "general"),
                "generated": d.get("generated", ""),
                "modified":  fmtime(p),
                "size":      p.stat().st_size,
            })
        except Exception:
            pass
    return jsonify(out)


@app.route("/api/reports/<name>")
def get_report(name):
    p = REPORTS / name
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify(json.loads(p.read_text()))


@app.route("/api/reports/<name>", methods=["DELETE"])
def del_report(name):
    p = REPORTS / name
    if p.exists():
        p.unlink()
    return jsonify({"success": True})


# ─── Logs ─────────────────────────────────────────────────────────────────────
@app.route("/api/logs")
def list_logs():
    logs = []
    for p in sorted(LOGS.glob("run_*.log"),
                    key=lambda x: x.stat().st_mtime, reverse=True)[:60]:
        logs.append({
            "name":     p.name,
            "size":     p.stat().st_size,
            "modified": fmtime(p),
        })
    return jsonify(logs)


@app.route("/api/logs/<name>")
def get_log(name):
    p = LOGS / name
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"name": name, "content": p.read_text(errors="replace")})


# ─── Boot: restore schedules ──────────────────────────────────────────────────
for _s in load_schedules():
    if _s.get("enabled"):
        register_schedule(_s)

log.info("mac-ops ready — %d schedule(s) loaded",
         sum(1 for s in load_schedules() if s.get("enabled")))

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
