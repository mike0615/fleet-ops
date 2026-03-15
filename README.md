# mac-ops — Maytag Ansible Console

**Author:** Mike Anderson  
**Version:** 1.1.0  
**License:** MIT  
**Platform:** Rocky Linux 9.7  

---

mac-ops is a self-hosted, browser-based Ansible management platform purpose-built for Maytag IT infrastructure. It replaces command-line Ansible operations with a polished web interface — write, validate, execute, schedule, and report on automation playbooks without direct CLI access.

**Designed for airgapped environments.** All frontend assets (CodeMirror editor, fonts) are bundled locally. No CDN dependencies at runtime.

---

## Features

- **Playbook Editor** — CodeMirror YAML editor with syntax highlighting, live validation, file browser with folder support, and 5 starter templates
- **Inventory Manager** — Browse, create, and edit INI/YAML inventory files
- **Cron Scheduler** — Automate playbook execution on cron schedules with pause/resume
- **Reports Viewer** — Structured collapsible viewer for system inventory and security audit reports
- **Run Logs** — Colorized ansible-playbook execution logs with PLAY RECAP parsing
- **Light & Dark Mode** — Full theme toggle with browser preference persistence
- **Airgap Ready** — Zero external dependencies at runtime; pip bundle support for installation

## Built-In Playbooks

| Playbook | Purpose |
|---|---|
| `system_inventory.yml` | Full HW, network, software, Docker inventory → JSON report |
| `security_audit.yml` | Login history, SSH keys, SUID files, firewall audit → JSON report (mode 600) |
| `system_maintenance.yml` | dnf update, kernel cleanup, log rotation, disk alerts |

---

## Quick Start

### Standard Install (requires internet)

```bash
# Transfer to Rocky 9.7 server
scp -r mac-ops/ root@YOUR_VM_IP:/tmp/

# On the server
cd /tmp/mac-ops
sudo bash install.sh

# Open browser
http://YOUR_VM_IP:5000
```

### Airgapped Install

```bash
# Step 1: On a connected machine with same OS/arch, bundle dependencies
bash prep-airgap.sh

# Step 2: Transfer entire mac-ops/ folder (including pip-packages/) to airgapped VM

# Step 3: On the airgapped machine
sudo bash install.sh --airgap
```

---

## Requirements

| Item | Minimum | Recommended |
|---|---|---|
| OS | Rocky Linux 9.3+ | Rocky Linux 9.7 |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 10 GB free | 20 GB free |

---

## Service Management

```bash
systemctl status  mac-ops
systemctl restart mac-ops
systemctl stop    mac-ops
journalctl -u mac-ops -f
```

---

## Directory Layout

```
/opt/mac-ops/
├── frontend/               # Web UI
│   ├── index.html          # Single-page application
│   └── vendor/codemirror/  # Bundled editor (airgap-safe)
├── backend/
│   └── app.py              # Flask REST API
├── ansible/
│   ├── playbooks/          # YAML playbooks
│   └── inventory/          # Host inventory files
├── reports/                # Generated JSON reports
├── logs/                   # Execution logs + mac-ops.log
└── venv/                   # Python virtual environment
```

---

## Post-Install: Add SSH Key to Managed Hosts

After installation, the installer prints a public key. Add it to every host you want to manage:

```bash
# View the key
cat /home/macops/.ssh/ansible_key.pub

# On each target host
echo 'PASTE_KEY_HERE' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## Security Hardening (Production)

For production deployments, place mac-ops behind Nginx with TLS:

```bash
dnf install -y nginx python3-certbot-nginx
# Configure /etc/nginx/conf.d/mac-ops.conf — see User Manual
certbot --nginx -d mac-ops.yourdomain.com
firewall-cmd --remove-port=5000/tcp --permanent
firewall-cmd --add-service=https --permanent && firewall-cmd --reload
```

---

## VS Code Development Setup

1. Open the `mac-ops/` folder in VS Code
2. Accept the recommended extensions prompt (see `.vscode/extensions.json`)
3. **Ctrl+Shift+P** → "Python: Select Interpreter" → choose `.venv`
4. Press **F5** to start the Flask backend with hot-reload
5. Open `http://localhost:5000`

---

## Changelog

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for full version history.

---

## License

MIT License — Copyright (c) 2025 Mike Anderson  
See [LICENSE](LICENSE) for details.
