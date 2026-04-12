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
import select
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, current_user
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import paramiko

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from models import db
from auth import init_login_manager
from auth_routes import register_auth_routes

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
def _configure_logging():
    """Configure logging for the application."""
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(LOGS / "mac-ops.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )

_configure_logging()
log = logging.getLogger("mac-ops")
log.info("mac-ops v1.1.0 starting — Author: Mike Anderson")

# ─── Global App Instance ──────────────────────────────────────────────────────
_app_instance = None
_socketio_instance = None
_scheduler_instance = None
_ssh_sessions: dict = {}
_ssh_lock = threading.Lock()


# ─── App ──────────────────────────────────────────────────────────────────────
# The production app/socketio/scheduler are initialized lazily, not at module import time.
# This allows tests to create fresh app instances without conflicts.

_production_app = None
_production_socketio = None
_production_scheduler = None


def _create_production_app():
    """Create the production singleton app instance."""
    global _production_app, _production_socketio, _production_scheduler
    
    if _production_app is None:
        _production_app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
        CORS(_production_app)
        _production_socketio = SocketIO(_production_app, cors_allowed_origins="*", 
                                        async_mode='threading',
                                        logger=False, engineio_logger=False)
        _production_scheduler = BackgroundScheduler(daemon=True)
        _production_scheduler.start()
        
        # Configure database for production (will be initialized in create_app)
        db_dir = Path('/var/lib/mac-ops')
        if not db_dir.exists():
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                db_dir = Path.home() / '.mac-ops'
                db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / 'mac.db'
        _production_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        _production_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        _production_app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
        # Only set SECURE flag if running over HTTPS (check environment or scheme)
        is_https = os.environ.get('HTTPS', '').lower() in ('true', '1', 'yes') or os.environ.get('SCHEME') == 'https'
        _production_app.config['SESSION_COOKIE_SECURE'] = is_https
        _production_app.config['SESSION_COOKIE_HTTPONLY'] = True
        _production_app.config['REMEMBER_COOKIE_SECURE'] = is_https
        _production_app.config['REMEMBER_COOKIE_HTTPONLY'] = True
        _production_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        
        # Initialize database and login manager
        db.init_app(_production_app)
        login_manager = LoginManager()
        init_login_manager(_production_app, login_manager)
        
        # Register authentication routes
        register_auth_routes(_production_app)
        
        # Initialize database
        with _production_app.app_context():
            db.create_all()
    
    return _production_app, _production_socketio, _production_scheduler


def create_app(testing: bool = False):
    """
    Application factory for creating Flask app instances.
    
    Args:
        testing: If True, create a fresh instance for testing (don't reuse singleton)
    
    Returns:
        Flask app instance with socketio attached
    """
    if testing:
        # For testing, create a fresh app instance each time
        app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
        CORS(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)
        return app
    
    # For production, use the singleton instance
    prod_app, _, _ = _create_production_app()
    return prod_app


# Lazy-initialize globals for production routes
def _get_app_globals():
    """Get app/socketio/scheduler for production mode."""
    return _create_production_app()


# These will be populated when first route is accessed
app, socketio, scheduler = None, None, None


def _init_globals():
    """Initialize global app, socketio, scheduler references on first access."""
    global app, socketio, scheduler
    if app is None:
        app, socketio, scheduler = _get_app_globals()

# ─── Helpers ─────────────────────────────────────────────────────────────────
# Routes will be registered on-demand when the app is first created

def load_schedules() -> list:
    if SCHED_FILE.exists():
        try:
            return json.loads(SCHED_FILE.read_text())
        except Exception:
            return []
    return []


def save_schedules(data: list) -> None:
    try:
        SCHED_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHED_FILE.write_text(json.dumps(data, indent=2))
    except PermissionError as exc:
        log.error("Permission denied writing schedules.json: %s", exc)
        raise
    except Exception as exc:
        log.error("Error writing schedules.json: %s", exc)
        raise


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


# ─── Initialize globals before defining routes ────────────────────────────────
_init_globals()


# ─── Static / index ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve app dashboard (redirects to login if not authenticated)."""
    if not current_user.is_authenticated:
        return send_from_directory(str(FRONTEND), "login.html")
    return send_from_directory(str(FRONTEND), "index.html")


@app.route("/logs")
def logs_page():
    """Serve the log reader page."""
    if not current_user.is_authenticated:
        return redirect("/login")
    return send_from_directory(str(FRONTEND), "logs.html")


@app.route("/login")
def login_page():
    """Serve login page."""
    if current_user.is_authenticated:
        # Redirect to dashboard if already logged in
        return send_from_directory(str(FRONTEND), "index.html")
    return send_from_directory(str(FRONTEND), "login.html")


@app.route("/auth/login", methods=["POST"])
def api_login():
    """API endpoint for user authentication.
    
    POST data should include:
        - username: Username
        - password: Password
        - auth_method: 'local', 'ldap', or 'auto' (default)
        - remember_me: boolean (optional)
    """
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        auth_method = data.get('auth_method', 'auto').lower()
        
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400
        
        # Import authentication helpers
        from auth import authenticate, AuthenticatedUser
        
        user, msg = authenticate(username, password, auth_method)
        if not user:
            return jsonify({"error": msg}), 401
        
        # Log in the user
        from flask_login import login_user
        auth_user = AuthenticatedUser(user)
        login_user(auth_user, remember=data.get('remember_me', False))
        
        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "auth_method": user.auth_method,
                "roles": [r.name for r in user.roles],
            }
        }), 200
    except Exception as e:
        log.error(f"Login error: {e}", exc_info=True)
        return jsonify({"error": "Login failed"}), 500


@app.route("/auth/logout", methods=["POST"])
def api_logout():
    """API endpoint for user logout."""
    from flask_login import logout_user
    logout_user()
    return jsonify({"message": "Logout successful"}), 200


@app.route("/auth/status", methods=["GET"])
def auth_status():
    """Check authentication system status (LDAP connectivity, etc)."""
    try:
        from config import get_config
        config = get_config()
        
        status = {
            "ldap_enabled": config.get('LDAP_ENABLED', False),
            "ldap_connected": False,
            "ldap_error": None
        }
        
        if status['ldap_enabled']:
            try:
                from ldap_auth import test_ldap_connection
                success, msg = test_ldap_connection()
                status['ldap_connected'] = success
                if not success:
                    status['ldap_error'] = msg
            except Exception as e:
                status['ldap_error'] = str(e)
        
        return jsonify(status), 200
    except Exception as e:
        log.error(f"Auth status error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
    try:
        p = PLAYBOOKS / name
        p.resolve().relative_to(PLAYBOOKS.resolve())
        p.parent.mkdir(parents=True, exist_ok=True)
        content = (request.json or {}).get("content", "")
        p.write_text(content)
        log.info("Saved playbook: %s", name)
        return jsonify({"success": True})
    except PermissionError as exc:
        log.error("Permission denied saving playbook %s: %s", name, exc)
        return jsonify({"error": f"Permission denied — run: sudo chown -R macops:macops /opt/mac-ops/ansible"}), 500
    except Exception as exc:
        log.error("Error saving playbook %s: %s", name, exc)
        return jsonify({"error": str(exc)}), 500


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
    try:
        p = INVENTORY / name
        # Prevent path traversal
        p.resolve().relative_to(INVENTORY.resolve())
        content = (request.json or {}).get("content", "")
        p.write_text(content)
        log.info("Saved inventory: %s", name)
        return jsonify({"success": True})
    except PermissionError as exc:
        log.error("Permission denied saving inventory %s: %s", name, exc)
        return jsonify({"error": f"Permission denied — run: sudo chown -R macops:macops /opt/mac-ops/ansible"}), 500
    except Exception as exc:
        log.error("Error saving inventory %s: %s", name, exc)
        return jsonify({"error": str(exc)}), 500


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
    try:
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
    except PermissionError:
        return jsonify({"error": "Permission denied — run: sudo chown -R macops:macops /opt/mac-ops/backend"}), 500
    except Exception as exc:
        log.exception("Error creating schedule")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/schedules/<sid>", methods=["DELETE"])
def del_schedule(sid):
    try:
        sl = [s for s in load_schedules() if s["id"] != sid]
        save_schedules(sl)
        try:
            scheduler.remove_job(sid)
        except Exception:
            pass
        return jsonify({"success": True})
    except PermissionError:
        return jsonify({"error": "Permission denied — run: sudo chown -R macops:macops /opt/mac-ops/backend"}), 500
    except Exception as exc:
        log.exception("Error deleting schedule %s", sid)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/schedules/<sid>/toggle", methods=["POST"])
def toggle_schedule(sid):
    try:
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
    except PermissionError:
        return jsonify({"error": "Permission denied — run: sudo chown -R macops:macops /opt/mac-ops/backend"}), 500
    except Exception as exc:
        log.exception("Error toggling schedule %s", sid)
        return jsonify({"error": str(exc)}), 500


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


# ─── Ad-hoc Runner ────────────────────────────────────────────────────────────
@app.route("/adhoc")
def adhoc_page():
    return send_from_directory(str(FRONTEND), "adhoc.html")


@app.route("/api/adhoc", methods=["POST"])
def api_adhoc():
    d       = request.json or {}
    pattern = d.get("pattern", "all").strip() or "all"
    module  = d.get("module",  "ping").strip() or "ping"
    args    = d.get("args",    "").strip()
    inv     = d.get("inventory", "")

    # Pick inventory file
    if inv:
        inv_path = INVENTORY / inv
    else:
        candidates = sorted(INVENTORY.glob("*.ini")) + sorted(INVENTORY.glob("*.yml"))
        inv_path = candidates[0] if candidates else INVENTORY / "hosts.ini"

    cmd = ["ansible", pattern, "-i", str(inv_path), "-m", module]
    if args:
        cmd += ["-a", args]
    cmd += ["-v"]

    log.info("Ad-hoc: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return jsonify({
            "success":    result.returncode == 0,
            "returncode": result.returncode,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timed out after 60 seconds"})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)})


# ─── Host Checker ─────────────────────────────────────────────────────────────
@app.route("/hostcheck")
def hostcheck_page():
    return send_from_directory(str(FRONTEND), "hostcheck.html")


@app.route("/api/hostcheck", methods=["POST"])
def api_hostcheck():
    import socket as _sock
    import re as _re
    hosts = [h.strip() for h in (request.json or {}).get("hosts", []) if h.strip()]
    if not hosts:
        return jsonify([])

    # Build a set of hosts mentioned in any inventory file
    inv_text = ""
    for f in list(INVENTORY.glob("*.ini")) + list(INVENTORY.glob("*.yml")):
        try:
            inv_text += f.read_text(errors="replace")
        except Exception:
            pass

    results = []
    for host in hosts:
        rec = {"host": host, "ping": False, "ssh": False,
               "inventory": False, "latency": None}

        # ICMP ping
        try:
            pr = subprocess.run(["ping", "-c", "1", "-W", "2", host],
                                capture_output=True, text=True, timeout=5)
            rec["ping"] = pr.returncode == 0
            if rec["ping"]:
                m = _re.search(r'time[=<](\d+\.?\d*)\s*ms', pr.stdout)
                if m:
                    rec["latency"] = float(m.group(1))
        except Exception:
            pass

        # TCP port 22
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            s.settimeout(3)
            rec["ssh"] = s.connect_ex((host, 22)) == 0
            s.close()
        except Exception:
            pass

        # In inventory?
        rec["inventory"] = host in inv_text

        results.append(rec)

    return jsonify(results)


# ─── SSH Console ──────────────────────────────────────────────────────────────

# ─── Logs ──────────────────────────────────────────────────────────────────────
@app.route("/api/logs")
def list_logs():
    """List all available log files."""
    try:
        logs = []
        if LOGS.exists():
            for log_file in sorted(LOGS.glob("*.log"), reverse=True):
                try:
                    stat = log_file.stat()
                    logs.append({
                        "name": log_file.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "path": str(log_file.relative_to(LOGS))
                    })
                except Exception:
                    pass
        return jsonify(logs)
    except Exception as exc:
        log.exception("Error listing logs")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/logs/<path:name>")
def read_log(name):
    """Read a specific log file with pagination."""
    try:
        # Prevent directory traversal
        if ".." in name or name.startswith("/"):
            return jsonify({"error": "Invalid log name"}), 400
        
        log_path = LOGS / name
        if not log_path.exists() or not log_path.is_file():
            return jsonify({"error": "Log file not found"}), 404
        
        # Get pagination parameters
        lines_param = request.args.get("lines", "100", type=int)
        lines_param = min(max(lines_param, 10), 1000)  # Clamp between 10-1000
        skip_lines = request.args.get("skip", "0", type=int)
        
        # Read file
        try:
            content = log_path.read_text(errors="replace")
        except Exception as exc:
            return jsonify({"error": f"Error reading log: {str(exc)}"}), 500
        
        all_lines = content.split("\n")
        total = len(all_lines)
        
        # Apply pagination
        start_idx = max(0, total - skip_lines - lines_param)
        end_idx = total - skip_lines
        
        lines = all_lines[start_idx:end_idx]
        
        return jsonify({
            "file": name,
            "size": log_path.stat().st_size,
            "total_lines": total,
            "lines": lines,
            "start": start_idx,
            "end": end_idx,
            "has_more": start_idx > 0
        })
    except Exception as exc:
        log.exception("Error reading log")
        return jsonify({"error": str(exc)}), 500

@app.route("/ssh-console")
def ssh_console_page():
    """Serve the web-based SSH terminal page."""
    return send_from_directory(str(FRONTEND), "ssh_console.html")


@socketio.on("connect", namespace="/ssh")
def ssh_ws_connect():
    log.info("SSH WebSocket connected: %s", request.sid)


@socketio.on("disconnect", namespace="/ssh")
def ssh_ws_disconnect():
    sid = request.sid
    with _ssh_lock:
        sess = _ssh_sessions.pop(sid, None)
    if sess:
        try:
            sess["channel"].close()
            sess["client"].close()
        except Exception:
            pass
    log.info("SSH WebSocket disconnected: %s", sid)


@socketio.on("connect_ssh", namespace="/ssh")
def ssh_ws_open(data):
    """Establish SSH connection and start background reader thread."""
    sid      = request.sid
    host     = data.get("host", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    port     = int(data.get("port", 22))

    if not host or not username:
        emit("error", {"message": "Host and username are required"})
        return

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=port, username=username,
                       password=password, timeout=10,
                       look_for_keys=False, allow_agent=False)
        channel = client.invoke_shell(term="xterm-256color", width=220, height=50)
        channel.setblocking(False)

        with _ssh_lock:
            _ssh_sessions[sid] = {"client": client, "channel": channel}

        emit("connected", {"message": f"Connected to {host}"})
        log.info("SSH session opened: %s -> %s@%s:%d", sid, username, host, port)

        def _read_loop():
            while True:
                with _ssh_lock:
                    if sid not in _ssh_sessions:
                        break
                    ch = _ssh_sessions[sid]["channel"]
                try:
                    ready, _, _ = select.select([ch], [], [], 0.1)
                    if ready:
                        chunk = ch.recv(4096)
                        if not chunk:
                            socketio.emit("disconnected",
                                          {"message": "Connection closed by remote host"},
                                          namespace="/ssh", to=sid)
                            break
                        socketio.emit("output",
                                      {"data": chunk.decode("utf-8", errors="replace")},
                                      namespace="/ssh", to=sid)
                    elif ch.closed:
                        socketio.emit("disconnected",
                                      {"message": "Channel closed"},
                                      namespace="/ssh", to=sid)
                        break
                except Exception as exc:
                    with _ssh_lock:
                        if sid in _ssh_sessions:
                            socketio.emit("error", {"message": str(exc)},
                                          namespace="/ssh", to=sid)
                    break

            with _ssh_lock:
                sess = _ssh_sessions.pop(sid, None)
            if sess:
                try:
                    sess["channel"].close()
                    sess["client"].close()
                except Exception:
                    pass

        threading.Thread(target=_read_loop, daemon=True).start()

    except paramiko.AuthenticationException:
        emit("error", {"message": "Authentication failed — check username and password"})
    except paramiko.SSHException as exc:
        emit("error", {"message": f"SSH error: {exc}"})
    except OSError as exc:
        emit("error", {"message": f"Connection failed: {exc}"})
    except Exception as exc:
        log.exception("SSH connect error")
        emit("error", {"message": f"Unexpected error: {exc}"})


@socketio.on("input", namespace="/ssh")
def ssh_ws_input(data):
    sid = request.sid
    with _ssh_lock:
        sess = _ssh_sessions.get(sid)
    if sess:
        try:
            sess["channel"].sendall(data.get("data", "").encode())
        except Exception as exc:
            emit("error", {"message": str(exc)})


@socketio.on("resize", namespace="/ssh")
def ssh_ws_resize(data):
    sid = request.sid
    with _ssh_lock:
        sess = _ssh_sessions.get(sid)
    if sess:
        try:
            sess["channel"].resize_pty(
                width=int(data.get("cols", 80)),
                height=int(data.get("rows", 24)),
            )
        except Exception:
            pass


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app_instance = create_app()
    socketio.run(app_instance, host="0.0.0.0", port=5000, debug=False,
                 allow_unsafe_werkzeug=True)
