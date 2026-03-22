#!/usr/bin/env bash
# =============================================================================
# LRN_PXE — Airgapped / Offline Installer
# Uses the pre-downloaded bundle/ directory — NO internet required.
#
# Prerequisites:
#   1. Run fetch-bundle.sh on an internet-connected Rocky Linux 9/10 machine
#   2. Run create-airgap-package.sh to produce lrn_pxe_offline_v*.tar.gz
#   3. Transfer the tarball to the target machine and extract it
#   4. Run: sudo bash install-offline.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

INSTALL_DIR="/opt/lrn_pxe"
TFTP_DIR="/var/lib/tftpboot"
SERVICE_NAME="lrn-pxe"
LOG_FILE="/var/log/lrn_pxe_install.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$SCRIPT_DIR/bundle"

log()  { echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOG_FILE"; }
info() { echo -e "${CYAN}[i]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOG_FILE"; exit 1; }
step() { echo -e "\n${BOLD}${BLUE}== $* ==${NC}" | tee -a "$LOG_FILE"; }

banner() {
cat << 'EOF'
  ██╗     ██████╗ ███╗   ██╗    ██████╗ ██╗  ██╗███████╗
  ██║     ██╔══██╗████╗  ██║    ██╔══██╗╚██╗██╔╝██╔════╝
  ██║     ██████╔╝██╔██╗ ██║    ██████╔╝ ╚███╔╝ █████╗
  ██║     ██╔══██╗██║╚██╗██║    ██╔═══╝  ██╔██╗ ██╔══╝
  ███████╗██║  ██║██║ ╚████║    ██║     ██╔╝ ██╗███████╗
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝    ╚═╝     ╚═╝  ╚═╝╚══════╝
          OFFLINE / AIRGAPPED INSTALLER  v1.0.0
EOF
}

# ── Pre-flight ────────────────────────────────────────────────────────────────
check_root() {
  [[ $EUID -eq 0 ]] || err "Must be run as root: sudo bash install-offline.sh"
}

check_os() {
  source /etc/os-release 2>/dev/null || err "Cannot detect OS"
  [[ "$ID" == "rocky" ]] || {
    warn "Detected: $PRETTY_NAME (designed for Rocky Linux 9/10)"
    read -rp "Continue anyway? [y/N]: " ans
    [[ "${ans,,}" == "y" ]] || exit 0
  }
  info "OS: $PRETTY_NAME"
}

check_bundle() {
  [[ -d "$BUNDLE_DIR" ]] || err "Bundle directory not found at $BUNDLE_DIR.

  Run 'sudo bash fetch-bundle.sh' on an internet-connected machine first,
  then transfer the full package to this machine."

  [[ -d "$BUNDLE_DIR/rpms" ]]       || err "bundle/rpms/ missing. Re-run fetch-bundle.sh."
  [[ -d "$BUNDLE_DIR/pip-wheels" ]] || err "bundle/pip-wheels/ missing. Re-run fetch-bundle.sh."
  [[ -d "$BUNDLE_DIR/ipxe" ]]       || err "bundle/ipxe/ missing. Re-run fetch-bundle.sh."
  [[ -d "$BUNDLE_DIR/vendor" ]]     || err "bundle/vendor/ missing. Re-run fetch-bundle.sh."

  RPM_COUNT=$(ls "$BUNDLE_DIR/rpms/"*.rpm 2>/dev/null | wc -l)
  WHEEL_COUNT=$(ls "$BUNDLE_DIR/pip-wheels/"* 2>/dev/null | wc -l)

  info "Bundle: $RPM_COUNT RPMs, $WHEEL_COUNT Python packages"
  [[ $RPM_COUNT -gt 0 ]] || err "No RPMs in bundle/rpms/. Re-run fetch-bundle.sh."

  if [[ -f "$BUNDLE_DIR/MANIFEST.txt" ]]; then
    info "Bundle manifest:"
    grep -E "^(Generated|Host OS|Bootstrap|RPM|Wheel)" "$BUNDLE_DIR/MANIFEST.txt" \
      | sed 's/^/    /'
  fi
}

# ── Network detection ─────────────────────────────────────────────────────────
detect_network() {
  PRIMARY_IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}' \
               || ip link | awk -F': ' '/^[0-9]+: [^lo]/{print $2; exit}')
  SERVER_IP=$(ip -4 addr show "$PRIMARY_IFACE" 2>/dev/null \
              | awk '/inet /{split($2,a,"/"); print a[1]}' | head -1)
  NETWORK_PREFIX=$(echo "$SERVER_IP" | awk -F. '{print $1"."$2"."$3}')

  [[ -n "$SERVER_IP" ]] || err "Could not detect server IP."
  info "Interface: $PRIMARY_IFACE / IP: $SERVER_IP"
}

# ── Interactive configuration ─────────────────────────────────────────────────
configure_interactive() {
  step "Network Configuration"
  echo ""
  echo -e "  ${BOLD}Press Enter to accept defaults, or type a new value:${NC}"
  echo ""

  read -rp "  PXE Server IP Address [$SERVER_IP]: " input
  SERVER_IP="${input:-$SERVER_IP}"

  read -rp "  Network Interface [$PRIMARY_IFACE]: " input
  PRIMARY_IFACE="${input:-$PRIMARY_IFACE}"

  DHCP_START="${NETWORK_PREFIX}.100"
  DHCP_END="${NETWORK_PREFIX}.200"
  DHCP_NETMASK="255.255.255.0"
  DHCP_GATEWAY="$SERVER_IP"
  DHCP_DNS="$SERVER_IP"
  WEB_PORT="8080"

  read -rp "  DHCP Range Start [$DHCP_START]: " input; DHCP_START="${input:-$DHCP_START}"
  read -rp "  DHCP Range End [$DHCP_END]: "   input; DHCP_END="${input:-$DHCP_END}"
  read -rp "  Subnet Mask [$DHCP_NETMASK]: "  input; DHCP_NETMASK="${input:-$DHCP_NETMASK}"
  read -rp "  Default Gateway [$DHCP_GATEWAY]: " input; DHCP_GATEWAY="${input:-$DHCP_GATEWAY}"
  read -rp "  DNS Server [$DHCP_DNS]: "        input; DHCP_DNS="${input:-$DHCP_DNS}"
  read -rp "  Web UI Port [$WEB_PORT]: "       input; WEB_PORT="${input:-$WEB_PORT}"

  echo ""
  echo -e "  ${BOLD}Configuration summary:${NC}"
  echo -e "  Server IP   : ${CYAN}$SERVER_IP${NC}"
  echo -e "  Interface   : ${CYAN}$PRIMARY_IFACE${NC}"
  echo -e "  DHCP Range  : ${CYAN}$DHCP_START - $DHCP_END${NC}"
  echo -e "  Web UI Port : ${CYAN}$WEB_PORT${NC}"
  echo ""
  read -rp "  Proceed? [Y/n]: " ans
  [[ "${ans,,}" != "n" ]] || exit 0
}

# ── Install RPMs from local bundle ────────────────────────────────────────────
install_packages_offline() {
  step "Installing RPM Packages (offline)"

  info "Configuring temporary local repository..."
  cat > /etc/yum.repos.d/lrn_pxe_bundle.repo << REPO
[lrn_pxe_bundle]
name=LRN_PXE Offline Bundle
baseurl=file://${BUNDLE_DIR}/rpms
enabled=1
gpgcheck=0
priority=1
REPO

  # Disable all other repos to avoid network calls
  info "Installing packages from bundle..."
  dnf install -y \
    --disablerepo='*' \
    --enablerepo='lrn_pxe_bundle' \
    dnsmasq nginx \
    python3 python3-pip python3-devel \
    gcc make perl perl-Data-Dumper \
    xz-devel binutils \
    genisoimage isomd5sum \
    curl wget rsync \
    lsof net-tools \
    firewalld \
    &>>"$LOG_FILE" && log "Packages installed from local bundle" \
    || {
      warn "Some packages not in bundle — trying with all repos enabled..."
      dnf install -y \
        dnsmasq nginx python3 python3-pip gcc make perl \
        genisoimage curl wget rsync lsof net-tools firewalld \
        &>>"$LOG_FILE" && log "Packages installed" || err "Package installation failed"
    }

  # Clean up temporary repo file
  rm -f /etc/yum.repos.d/lrn_pxe_bundle.repo
}

# ── Install iPXE binaries ─────────────────────────────────────────────────────
install_ipxe_offline() {
  step "Installing iPXE Binaries"

  mkdir -p "$TFTP_DIR/ipxe"

  # Try building from source first (if build tools available)
  IPXE_SRC=""
  for candidate in \
    "$SCRIPT_DIR/iPXE/ipxe-bd13697/src" \
    "$SCRIPT_DIR/../iPXE/ipxe-bd13697/src"; do
    if [[ -d "$candidate" && -f "$candidate/Makefile" ]]; then
      IPXE_SRC="$candidate"
      break
    fi
  done

  if [[ -n "$IPXE_SRC" ]] && command -v gcc &>/dev/null; then
    info "Building iPXE from source..."
    cat > /tmp/lrn_pxe_boot.ipxe << IPXE
#!ipxe
:retry
dhcp || goto retry
chain http://${SERVER_IP}:${WEB_PORT}/menu.ipxe || shell
IPXE
    make -C "$IPXE_SRC" bin/undionly.kpxe EMBED=/tmp/lrn_pxe_boot.ipxe \
      -j"$(nproc)" &>>"$LOG_FILE" \
      && cp "$IPXE_SRC/bin/undionly.kpxe" "$TFTP_DIR/ipxe/" \
      && log "Built undionly.kpxe from source" \
      || { warn "BIOS build failed — using bundled binary"; copy_bundled_bios; }

    make -C "$IPXE_SRC" bin-x86_64-efi/ipxe.efi EMBED=/tmp/lrn_pxe_boot.ipxe \
      -j"$(nproc)" &>>"$LOG_FILE" \
      && cp "$IPXE_SRC/bin-x86_64-efi/ipxe.efi" "$TFTP_DIR/ipxe/" \
      && log "Built ipxe.efi from source" \
      || { warn "UEFI build failed — using bundled binary"; copy_bundled_uefi; }
  else
    info "Using pre-built iPXE binaries from bundle..."
    copy_bundled_bios
    copy_bundled_uefi
  fi
}

copy_bundled_bios() {
  [[ -f "$BUNDLE_DIR/ipxe/undionly.kpxe" ]] \
    && cp "$BUNDLE_DIR/ipxe/undionly.kpxe" "$TFTP_DIR/ipxe/" \
    && log "Installed undionly.kpxe from bundle" \
    || err "undionly.kpxe not found in bundle. Re-run fetch-bundle.sh."
}

copy_bundled_uefi() {
  [[ -f "$BUNDLE_DIR/ipxe/ipxe.efi" ]] \
    && cp "$BUNDLE_DIR/ipxe/ipxe.efi" "$TFTP_DIR/ipxe/" \
    && log "Installed ipxe.efi from bundle" \
    || err "ipxe.efi not found in bundle. Re-run fetch-bundle.sh."
}

# ── Create directories ────────────────────────────────────────────────────────
create_directories() {
  step "Creating Directory Structure"
  mkdir -p \
    "$INSTALL_DIR/isos" \
    "$INSTALL_DIR/kickstarts" \
    "$INSTALL_DIR/boot" \
    "$INSTALL_DIR/mounts" \
    "$INSTALL_DIR/config" \
    "$INSTALL_DIR/web" \
    "$INSTALL_DIR/logs"

  # Install web app
  [[ -d "$SCRIPT_DIR/web" ]] && cp -r "$SCRIPT_DIR/web/." "$INSTALL_DIR/web/"

  # Install vendor assets (Bootstrap + Icons) into web static
  if [[ -d "$BUNDLE_DIR/vendor" ]]; then
    mkdir -p "$INSTALL_DIR/web/static/vendor"
    cp -r "$BUNDLE_DIR/vendor/." "$INSTALL_DIR/web/static/vendor/"
    log "Frontend vendor assets installed (offline mode)"
  fi

  log "Directories created"
}

# ── Config files ──────────────────────────────────────────────────────────────
create_initial_config() {
  step "Writing Configuration Files"

  cat > "$INSTALL_DIR/config/menu.json" << JSON
{
  "title": "LRN_PXE Boot Menu",
  "timeout": 60,
  "default": "",
  "entries": []
}
JSON

  cat > "$INSTALL_DIR/config/settings.json" << JSON
{
  "server_ip": "${SERVER_IP}",
  "web_port": ${WEB_PORT},
  "dhcp_enabled": true,
  "dhcp_interface": "${PRIMARY_IFACE}",
  "dhcp_start": "${DHCP_START}",
  "dhcp_end": "${DHCP_END}",
  "dhcp_netmask": "${DHCP_NETMASK}",
  "dhcp_gateway": "${DHCP_GATEWAY}",
  "dhcp_dns": "${DHCP_DNS}",
  "dhcp_lease_time": "12h",
  "version": "1.0.0",
  "offline_mode": true
}
JSON
  log "Config files written"
}

# ── Python venv + Flask (offline) ─────────────────────────────────────────────
setup_python_app_offline() {
  step "Setting Up Python Application (offline)"

  python3 -m venv "$INSTALL_DIR/venv" &>>"$LOG_FILE" && log "venv created"

  info "Installing Python packages from local wheel bundle..."
  "$INSTALL_DIR/venv/bin/pip" install \
    --no-index \
    --find-links="$BUNDLE_DIR/pip-wheels" \
    flask flask-cors \
    &>>"$LOG_FILE" && log "Flask installed from bundle" \
    || err "Flask install failed. Check $LOG_FILE — ensure fetch-bundle.sh completed."

  log "Python app set up"
}

# ── dnsmasq ───────────────────────────────────────────────────────────────────
configure_dnsmasq() {
  step "Configuring dnsmasq (DHCP + TFTP)"

  [[ -f /etc/dnsmasq.conf ]] && cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bak.$(date +%s)

  cat > /etc/dnsmasq.d/lrn_pxe.conf << DNSMASQ
# LRN_PXE dnsmasq configuration (offline install)
interface=${PRIMARY_IFACE}
bind-interfaces
except-interface=lo
dhcp-range=${DHCP_START},${DHCP_END},${DHCP_NETMASK},12h
dhcp-option=option:router,${DHCP_GATEWAY}
dhcp-option=option:dns-server,${DHCP_DNS}
enable-tftp
tftp-root=${TFTP_DIR}
dhcp-match=set:ipxe,175
dhcp-match=set:efi-x86_64,option:client-arch,7
dhcp-match=set:efi-x86_64,option:client-arch,9
dhcp-boot=tag:ipxe,http://${SERVER_IP}:${WEB_PORT}/menu.ipxe
dhcp-boot=tag:efi-x86_64,tag:!ipxe,ipxe/ipxe.efi,pxeserver,${SERVER_IP}
dhcp-boot=tag:!efi-x86_64,tag:!ipxe,ipxe/undionly.kpxe,pxeserver,${SERVER_IP}
dhcp-option=66,${SERVER_IP}
log-dhcp
log-facility=/var/log/dnsmasq.log
DNSMASQ

  systemctl enable dnsmasq &>>"$LOG_FILE"
  systemctl restart dnsmasq &>>"$LOG_FILE" && log "dnsmasq configured and started" \
    || err "dnsmasq failed to start — check: journalctl -u dnsmasq"
}

# ── nginx ─────────────────────────────────────────────────────────────────────
configure_nginx() {
  step "Configuring nginx"

  [[ -f /etc/nginx/nginx.conf ]] && cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak.$(date +%s)
  [[ -f /etc/nginx/conf.d/default.conf ]] \
    && mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.disabled

  cat > /etc/nginx/conf.d/lrn_pxe.conf << NGINX
server {
    listen 80 default_server;
    server_name _;
    root ${INSTALL_DIR};
    access_log /var/log/nginx/lrn_pxe_access.log;
    error_log  /var/log/nginx/lrn_pxe_error.log;

    location /isos/       { alias ${INSTALL_DIR}/isos/;       autoindex on; autoindex_exact_size off; }
    location /boot/       { alias ${INSTALL_DIR}/boot/;       autoindex on; }
    location /kickstarts/ { alias ${INSTALL_DIR}/kickstarts/; autoindex on; }
    location /mounts/     { alias ${INSTALL_DIR}/mounts/;     autoindex on; autoindex_exact_size off; }

    location / {
        proxy_pass         http://127.0.0.1:${WEB_PORT};
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_read_timeout 300;
        client_max_body_size 50G;
    }
}
NGINX

  nginx -t &>>"$LOG_FILE" && log "nginx config valid"
  systemctl enable nginx &>>"$LOG_FILE"
  systemctl restart nginx &>>"$LOG_FILE" && log "nginx started" \
    || err "nginx failed to start"
}

# ── systemd service ───────────────────────────────────────────────────────────
install_service() {
  step "Installing systemd Service"

  cp "$SCRIPT_DIR/systemd/lrn-pxe.service" /etc/systemd/system/ 2>/dev/null || \
  cat > /etc/systemd/system/lrn-pxe.service << SYSTEMD
[Unit]
Description=LRN_PXE Web Management Interface
After=network.target nginx.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}/web
Environment="FLASK_ENV=production"
Environment="LRN_PXE_DIR=${INSTALL_DIR}"
Environment="LRN_PXE_PORT=${WEB_PORT}"
ExecStart=${INSTALL_DIR}/venv/bin/python app.py
Restart=always
RestartSec=5
StandardOutput=append:${INSTALL_DIR}/logs/web.log
StandardError=append:${INSTALL_DIR}/logs/web_error.log

[Install]
WantedBy=multi-user.target
SYSTEMD

  # Patch the port into the service if needed
  sed -i "s/LRN_PXE_PORT=.*/LRN_PXE_PORT=${WEB_PORT}/" /etc/systemd/system/lrn-pxe.service

  systemctl daemon-reload &>>"$LOG_FILE"
  systemctl enable lrn-pxe &>>"$LOG_FILE"
  systemctl start  lrn-pxe &>>"$LOG_FILE" && log "lrn-pxe service started" \
    || err "Service failed to start — check: journalctl -u lrn-pxe"
}

# ── Firewall ──────────────────────────────────────────────────────────────────
configure_firewall() {
  step "Configuring Firewall"
  systemctl enable --now firewalld &>>"$LOG_FILE" 2>&1 || true
  firewall-cmd --permanent --add-service=dhcp   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-service=tftp   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-service=http   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-port="${WEB_PORT}/tcp" &>>"$LOG_FILE"
  firewall-cmd --reload &>>"$LOG_FILE"
  log "Firewall rules applied"
}

# ── SELinux ───────────────────────────────────────────────────────────────────
configure_selinux() {
  if command -v getenforce &>/dev/null && [[ "$(getenforce)" != "Disabled" ]]; then
    step "Configuring SELinux"
    setsebool -P httpd_can_network_connect 1  &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/isos"       &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/boot"       &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/kickstarts" &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/mounts"     &>>"$LOG_FILE" || true
    log "SELinux contexts set"
  fi
}

# ── CLI tool ──────────────────────────────────────────────────────────────────
install_cli() {
  [[ -f "$SCRIPT_DIR/scripts/lrn-pxe-cli.sh" ]] && {
    cp "$SCRIPT_DIR/scripts/lrn-pxe-cli.sh" /usr/local/bin/lrn-pxe
    chmod +x /usr/local/bin/lrn-pxe
    log "CLI tool installed at /usr/local/bin/lrn-pxe"
  }
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "${GREEN}${BOLD}+====================================================+${NC}"
  echo -e "${GREEN}${BOLD}|      LRN_PXE Offline Installation Complete!  ✓     |${NC}"
  echo -e "${GREEN}${BOLD}+====================================================+${NC}"
  echo ""
  echo -e "  ${BOLD}Web Management UI:${NC}"
  echo -e "  ${CYAN}http://${SERVER_IP}/${NC}"
  echo ""
  echo -e "  ${BOLD}Key Directories:${NC}"
  echo -e "  ISOs:        $INSTALL_DIR/isos/"
  echo -e "  Kickstarts:  $INSTALL_DIR/kickstarts/"
  echo -e "  Boot files:  $INSTALL_DIR/boot/"
  echo -e "  iPXE bins:   $TFTP_DIR/ipxe/"
  echo ""
  echo -e "  ${BOLD}Services:${NC}"
  echo -e "  ${CYAN}systemctl status lrn-pxe dnsmasq nginx${NC}"
  echo ""
  echo -e "  ${BOLD}CLI:${NC}  ${CYAN}lrn-pxe --help${NC}"
  echo ""
  echo -e "  ${YELLOW}Note:${NC} Installed in offline mode — web UI uses bundled"
  echo -e "  Bootstrap assets (no CDN required)."
  echo ""
  echo -e "  Install log: $LOG_FILE"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  touch "$LOG_FILE"
  clear
  banner

  check_root
  check_os
  check_bundle
  detect_network
  configure_interactive

  log "Starting offline installation — logging to $LOG_FILE"

  install_packages_offline
  install_ipxe_offline
  create_directories
  create_initial_config
  setup_python_app_offline
  configure_dnsmasq
  configure_nginx
  install_service
  configure_firewall
  configure_selinux
  install_cli
  print_summary
}

main "$@"
