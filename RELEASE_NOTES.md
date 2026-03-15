# mac-ops Release Notes

**Author:** Mike Anderson  
**Project:** Maytag Ansible Console (mac-ops)

---

## v1.1.0 — 2025-03-15

### Summary
Major update introducing full airgap support, file browser, and production hardening.

### New Features
- **Airgap deployment** — All CDN dependencies removed. CodeMirror assets are now bundled locally under `frontend/vendor/codemirror/`. No internet access required at runtime.
- **`prep-airgap.sh`** — New preparation script downloads all pip wheel files (`flask`, `ansible-core`, `apscheduler`, etc.) into a `pip-packages/` bundle for fully offline installation.
- **`install.sh --airgap`** — Flag installs all Python packages from the local bundle instead of PyPI.
- **File browser — Playbooks** — Full recursive directory tree in the Playbooks editor sidebar. Create sub-folders, expand/collapse directories, click to open any file. Supports nested playbook organization (e.g. `linux/`, `networking/`, `docker/`).
- **File browser — Inventory** — Browse, open, and manage inventory files from a live file listing with in-place editing.
- **New Folder button** — Create subdirectory structure in the playbooks tree via the UI.
- **Path breadcrumb bar** — Shows full relative path of the currently open file (`ansible/playbooks/linux/setup.yml`).
- **`/api/browse/playbooks`** — New API endpoint returning recursive directory tree (dirs + files).
- **`/api/browse/inventory`** — New API endpoint for inventory file listing.
- **`/api/playbooks/mkdir`** — New API endpoint to create subdirectories.

### Changes
- **AI Assistant removed** — Tab and all associated JS/API code removed. Not appropriate for airgapped environments.
- **Branding updated** — All references to `ansibleops` and `AnsibleOps` replaced with `mac-ops` and `mac-ops`. Install path changed from `/opt/mac` to `/opt/mac-ops`. Service renamed from `mac.service` to `mac-ops.service`.
- **Font stack** — Google Fonts (IBM Plex Mono, Epilogue) removed. Replaced with system font stack (`Consolas/Courier New` mono, `Segoe UI/Helvetica` sans). No external font requests.
- **`app.py` rewritten** — Full Python docstring with author, version, and license. Improved logging format. All route handlers documented.
- **Author header** — `# Author: Mike Anderson` and version comment added to all source files.
- **Settings panel** — About section updated to reflect v1.1.0 and airgap status.

### Bug Fixes
- Fixed `openRunModal` and `openSchedModal` to use `/api/browse/inventory` for correct file listing
- Fixed editor `clearHistory()` call on file open to prevent undo contamination across files
- Fixed `refreshPBTree()` to reload tree without losing editor state

### Security
- `prep-airgap.sh` validates same OS/arch to prevent architecture mismatch in pip wheels
- Security audit report path updated to `/opt/mac-ops/reports/`

---

## v1.0.1 — 2025-03-14

### Summary
Hotfix for EPEL dependency failure during installation.

### Bug Fixes
- **Critical:** Removed `python3-virtualenv` from the `dnf install` block. The EPEL 9 package has a broken dependency: `python3-virtualenv → python3-wheel-wheel` (missing in Rocky 9). Installation now uses Python stdlib `venv` module (`python3 -m venv`) which is built into Python 3.9+ and requires no separate package.
- Removed `ansible` and `ansible-core` from the `dnf install` block entirely. Both are now installed via `pip install ansible-core` into the venv, bypassing the EPEL dependency chain completely.
- `ansible-playbook`, `ansible`, and `ansible-galaxy` symlinked to `/usr/local/bin` after pip install.
- Sudoers updated to reference `/usr/local/bin/ansible-playbook` instead of `/usr/bin/`.
- `systemd` service `Environment=PATH` updated to include venv bin directory.

---

## v1.0.0 — 2025-03-14

### Summary
Initial release of the Maytag Ansible Console (mac-ops).

### Features
- Browser-based YAML playbook editor (CodeMirror 5, material-darker theme)
- Inventory file manager (INI/YAML formats)
- Cron-based job scheduler with APScheduler (persists across restarts)
- System Inventory playbook — full HW, network, software, Docker → JSON report
- Security Audit playbook — login history, SSH, SUID, firewall → JSON report (mode 600)
- System Maintenance playbook — dnf update, kernel cleanup, log rotation
- Execution log viewer with colorized PLAY RECAP parsing
- Light/dark mode toggle (localStorage persistence)
- Bitmoji mascot with contextual reactions
- MAC logo (Maytag Ansible Console branding)
- `install.sh` for Rocky Linux 9.x (one-command deployment)
- systemd service (`mac-ops.service`) with auto-start
- firewalld integration (port 5000)
- APScheduler cron scheduling
- AI Assistant (Claude API) — *removed in v1.1.0*

---

## Roadmap

- [ ] HTTPS/TLS built-in (self-signed cert option)
- [ ] Role-based file organization templates
- [ ] Multi-host parallel run progress view
- [ ] Report comparison (diff between two inventory runs)
- [ ] Playbook import from Git repository (connected mode)
- [ ] Ansible Vault integration
- [ ] Email notifications on scheduled run completion
