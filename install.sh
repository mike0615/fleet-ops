#!/bin/bash
# =============================================================================
# mac-ops — Maytag Ansible Console
# Installation Script for Rocky Linux 9.x
# =============================================================================
# Author  : Mike Anderson
# Version : 1.1.0
# License : MIT
#
# Usage (connected install):
#   sudo bash install.sh
#
# Usage (airgapped install — run prep-airgap.sh first on a connected machine):
#   sudo bash install.sh --airgap
#
# What this script does:
#   1. Installs base OS packages from BaseOS/AppStream (no EPEL)
#   2. Creates /opt/mac-ops directory structure
#   3. Copies application files from the package
#   4. Builds Python venv and installs Flask + ansible-core via pip
#      (airgap mode: installs from bundled ./pip-packages/ directory)
#   5. Generates SSH key pair for Ansible
#   6. Writes /etc/ansible/ansible.cfg
#   7. Registers and starts mac-ops.service (systemd)
#   8. Opens firewall port 5000
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
CYN='\033[0;36m'; BLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${GRN}[✓]${NC} $*"; }
warn() { echo -e "${YLW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
sec()  { echo -e "\n${CYN}${BLD}── $* ──${NC}"; }

# ── Args ──────────────────────────────────────────────────────────────────────
AIRGAP=false
for arg in "$@"; do
  [[ "$arg" == "--airgap" ]] && AIRGAP=true
done

# ── Verify root ───────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash install.sh"

# ── Variables ─────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/mac-ops"
SVC_USER="macops"
SVC_NAME="mac-ops"
PORT=5000
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIP_PKG_DIR="${SRC}/pip-packages"

echo -e "${BLD}${CYN}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   mac-ops — Maytag Ansible Console v1.1  ║"
echo "  ║   Author: Mike Anderson                   ║"
echo "  ║   Rocky Linux 9  ·  $([ "$AIRGAP" = true ] && echo "AIRGAP MODE" || echo "ONLINE MODE ")        ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

if $AIRGAP; then
  warn "Airgap mode — all packages installed from local bundles"
  [[ -d "$PIP_PKG_DIR" ]] || die "pip-packages/ directory not found. Run prep-airgap.sh first."
  warn "pip-packages/ found: $(ls "$PIP_PKG_DIR"/*.whl 2>/dev/null | wc -l) wheels"
fi

# ── Step 1: Base OS packages ──────────────────────────────────────────────────
sec "Step 1: Installing Base OS Packages"

# Enable CRB for python3-devel on minimal installs
dnf install -y 'dnf-command(config-manager)' -q 2>/dev/null || true
dnf config-manager --set-enabled crb 2>/dev/null || \
  dnf config-manager --set-enabled powertools 2>/dev/null || true

# Install from BaseOS/AppStream only — no EPEL, no virtualenv
# ansible-core is installed via pip to avoid the python3-wheel-wheel EPEL bug
dnf install -y \
    python3 python3-pip python3-devel \
    git curl wget jq \
    sshpass openssh-clients \
    lsof net-tools \
    pciutils usbutils dmidecode \
    -q

log "Base OS packages installed"
python3 -c "import venv" || die "python3 venv module missing — run: dnf reinstall python3"

# ── Step 2: Service user ──────────────────────────────────────────────────────
sec "Step 2: Creating Service User: ${SVC_USER}"
if ! id "$SVC_USER" &>/dev/null; then
    useradd -r -m -d "/home/${SVC_USER}" -s /bin/bash "$SVC_USER"
    log "User created: ${SVC_USER}"
else
    warn "User ${SVC_USER} already exists — skipping"
fi
usermod -aG wheel  "$SVC_USER" 2>/dev/null || true
usermod -aG docker "$SVC_USER" 2>/dev/null || true

# ── Step 3: Directory structure ───────────────────────────────────────────────
sec "Step 3: Creating Directory Structure at ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"/{frontend/{vendor/codemirror,static},backend,ansible/{playbooks,inventory,roles},reports,logs}
log "Directories created"

# ── Step 4: Copy application files ───────────────────────────────────────────
sec "Step 4: Copying Application Files"
cp -r "${SRC}/backend/."           "${INSTALL_DIR}/backend/"
cp -r "${SRC}/frontend/."          "${INSTALL_DIR}/frontend/"
cp -r "${SRC}/ansible/playbooks/." "${INSTALL_DIR}/ansible/playbooks/"  2>/dev/null || true
cp -r "${SRC}/ansible/inventory/." "${INSTALL_DIR}/ansible/inventory/"  2>/dev/null || true

chown -R "${SVC_USER}:${SVC_USER}" "${INSTALL_DIR}"
chmod -R 755 "${INSTALL_DIR}"
chmod 700 "${INSTALL_DIR}/reports" "${INSTALL_DIR}/logs"
log "Application files copied"

# ── Step 5: Python virtual environment ───────────────────────────────────────
sec "Step 5: Building Python Virtual Environment"

python3 -m venv "${INSTALL_DIR}/venv"
VENV_PIP="${INSTALL_DIR}/venv/bin/pip"

"${VENV_PIP}" install --upgrade pip --quiet

if $AIRGAP; then
    log "Installing from local pip-packages/ (airgap mode)..."
    "${VENV_PIP}" install \
        --no-index \
        --find-links="${PIP_PKG_DIR}" \
        flask flask-cors "apscheduler>=3.10,<4" pyyaml ansible-core \
        --quiet
else
    log "Installing from PyPI (online mode)..."
    "${VENV_PIP}" install \
        "flask>=3.0,<4" \
        "flask-cors>=4.0" \
        "apscheduler>=3.10,<4" \
        "pyyaml>=6.0" \
        "ansible-core>=2.15" \
        --quiet
fi

# Symlink ansible to /usr/local/bin
for BIN in ansible ansible-playbook ansible-galaxy ansible-doc; do
    BPATH="${INSTALL_DIR}/venv/bin/${BIN}"
    [[ -f "$BPATH" ]] && ln -sf "$BPATH" "/usr/local/bin/${BIN}"
done
log "Ansible symlinked to /usr/local/bin"

ANSIBLE_VER=$("${INSTALL_DIR}/venv/bin/ansible" --version 2>/dev/null | head -1)
log "Installed: ${ANSIBLE_VER}"

chown -R "${SVC_USER}:${SVC_USER}" "${INSTALL_DIR}/venv"

# ── Step 6: SSH key pair ──────────────────────────────────────────────────────
sec "Step 6: Generating Ansible SSH Key Pair"
SSH_DIR="/home/${SVC_USER}/.ssh"
mkdir -p "$SSH_DIR"
if [[ ! -f "${SSH_DIR}/ansible_key" ]]; then
    ssh-keygen -t ed25519 -f "${SSH_DIR}/ansible_key" -N "" \
        -C "macops@$(hostname -s)" -q
    chmod 700 "$SSH_DIR"
    chmod 600 "${SSH_DIR}/ansible_key"
    chmod 644 "${SSH_DIR}/ansible_key.pub"
    chown -R "${SVC_USER}:${SVC_USER}" "$SSH_DIR"
    log "SSH key generated: ${SSH_DIR}/ansible_key"
    echo ""
    warn "▶ PUBLIC KEY — copy to ~/.ssh/authorized_keys on every managed host:"
    echo -e "${YLW}$(cat "${SSH_DIR}/ansible_key.pub")${NC}"
    echo ""
else
    warn "SSH key already exists — skipping"
fi

# ── Step 7: Ansible config ────────────────────────────────────────────────────
sec "Step 7: Writing Ansible Configuration"
mkdir -p /etc/ansible
cat > /etc/ansible/ansible.cfg << EOF
# mac-ops Ansible Configuration
# Author  : Mike Anderson
# Version : 1.1.0

[defaults]
inventory           = ${INSTALL_DIR}/ansible/inventory/hosts.ini
roles_path          = ${INSTALL_DIR}/ansible/roles
host_key_checking   = False
retry_files_enabled = False
stdout_callback     = yaml
forks               = 10
timeout             = 30
log_path            = ${INSTALL_DIR}/logs/ansible.log

[ssh_connection]
pipelining          = True
ssh_args            = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=no
EOF
log "Ansible config written to /etc/ansible/ansible.cfg"

# ── Step 8: systemd service ───────────────────────────────────────────────────
sec "Step 8: Installing systemd Service (${SVC_NAME}.service)"
cat > /etc/systemd/system/${SVC_NAME}.service << EOF
[Unit]
Description=mac-ops Maytag Ansible Console v1.1.0
After=network.target
# Author: Mike Anderson

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_USER}
WorkingDirectory=${INSTALL_DIR}/backend
ExecStart=${INSTALL_DIR}/venv/bin/python app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${INSTALL_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SVC_NAME}"
systemctl start  "${SVC_NAME}"
sleep 2
if systemctl is-active --quiet "${SVC_NAME}"; then
    log "${SVC_NAME}.service started ✓"
else
    warn "Service may not have started — check: journalctl -u ${SVC_NAME} -n 50 --no-pager"
fi

# ── Step 9: Firewall ──────────────────────────────────────────────────────────
sec "Step 9: Opening Firewall Port ${PORT}/tcp"
if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port="${PORT}/tcp"
    firewall-cmd --reload
    log "Port ${PORT}/tcp opened"
else
    warn "firewalld not running — open port manually if needed"
fi

# ── Step 10: Sudoers ──────────────────────────────────────────────────────────
sec "Step 10: Configuring Sudoers"
cat > /etc/sudoers.d/macops << 'EOF'
# mac-ops — Maytag Ansible Console
# Author: Mike Anderson
macops ALL=(ALL) NOPASSWD: /usr/local/bin/ansible-playbook
macops ALL=(ALL) NOPASSWD: /usr/local/bin/ansible
macops ALL=(ALL) NOPASSWD: /usr/local/bin/ansible-galaxy
EOF
chmod 440 /etc/sudoers.d/macops
visudo -c -f /etc/sudoers.d/macops && log "Sudoers validated" || warn "Check /etc/sudoers.d/macops"

# ── Step 11: Logrotate ────────────────────────────────────────────────────────
cat > /etc/logrotate.d/mac-ops << EOF
${INSTALL_DIR}/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 ${SVC_USER} ${SVC_USER}
}
EOF
log "Log rotation configured"

# ── Step 12: Smoke test ───────────────────────────────────────────────────────
sec "Step 12: API Smoke Test"
sleep 2
if curl -sf "http://localhost:${PORT}/api/dashboard" -o /dev/null; then
    log "API responding at http://localhost:${PORT} ✓"
else
    warn "API not yet responding — check: journalctl -u ${SVC_NAME} -n 30 --no-pager"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo -e "${GRN}${BLD}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║    mac-ops Installation Complete ✅       ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "${BLD}Open in browser:${NC}"
echo -e "  ${CYN}http://${IP}:${PORT}${NC}"
echo -e "  ${CYN}http://localhost:${PORT}${NC}"
echo ""
echo -e "${BLD}Key paths:${NC}"
echo -e "  App root:   ${INSTALL_DIR}"
echo -e "  Playbooks:  ${INSTALL_DIR}/ansible/playbooks/"
echo -e "  Inventory:  ${INSTALL_DIR}/ansible/inventory/"
echo -e "  Reports:    ${INSTALL_DIR}/reports/"
echo -e "  Logs:       ${INSTALL_DIR}/logs/"
echo -e "  SSH key:    /home/${SVC_USER}/.ssh/ansible_key.pub"
echo ""
echo -e "${BLD}Service commands:${NC}"
echo -e "  systemctl status  ${SVC_NAME}"
echo -e "  systemctl restart ${SVC_NAME}"
echo -e "  journalctl -u ${SVC_NAME} -f"
echo ""
echo -e "${YLW}▶ NEXT: Add the SSH public key shown above to ~/.ssh/authorized_keys"
echo -e "  on each host you want mac-ops to manage.${NC}"
