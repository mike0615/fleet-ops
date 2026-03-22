#!/usr/bin/env bash
# =============================================================================
# LRN_PXE - PXE Boot Server Installer
# Version: 1.0.0
# Supports: Rocky Linux 9 / Rocky Linux 10
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# ── Constants ─────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/lrn_pxe"
TFTP_DIR="/var/lib/tftpboot"
SERVICE_NAME="lrn-pxe"
WEB_PORT="8080"
LOG_FILE="/var/log/lrn_pxe_install.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Logging ───────────────────────────────────────────────────────────────────
log()  { echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOG_FILE"; }
info() { echo -e "${CYAN}[i]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOG_FILE"; exit 1; }
step() { echo -e "\n${BOLD}${BLUE}══ $* ══${NC}" | tee -a "$LOG_FILE"; }

banner() {
cat << 'EOF'
  ██╗     ██████╗ ███╗   ██╗    ██████╗ ██╗  ██╗███████╗
  ██║     ██╔══██╗████╗  ██║    ██╔══██╗╚██╗██╔╝██╔════╝
  ██║     ██████╔╝██╔██╗ ██║    ██████╔╝ ╚███╔╝ █████╗
  ██║     ██╔══██╗██║╚██╗██║    ██╔═══╝  ██╔██╗ ██╔══╝
  ███████╗██║  ██║██║ ╚████║    ██║     ██╔╝ ██╗███████╗
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝    ╚═╝     ╚═╝  ╚═╝╚══════╝
            Network Boot Server  •  v1.0.0
EOF
  echo -e "${CYAN}  PXE Boot Environment for Rocky Linux 9/10${NC}"
  echo -e "  ─────────────────────────────────────────────"
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
check_root() {
  [[ $EUID -eq 0 ]] || err "This installer must be run as root. Try: sudo bash install.sh"
}

check_os() {
  if [[ ! -f /etc/os-release ]]; then
    err "Cannot detect OS. Rocky Linux 9 or 10 is required."
  fi
  source /etc/os-release
  if [[ "$ID" != "rocky" ]]; then
    warn "This installer is designed for Rocky Linux. Detected: $PRETTY_NAME"
    read -rp "Continue anyway? [y/N]: " ans
    [[ "${ans,,}" == "y" ]] || exit 0
  fi
  OS_VERSION="${VERSION_ID%%.*}"
  info "Detected OS: $PRETTY_NAME"
}

detect_network() {
  # Find primary non-loopback interface
  PRIMARY_IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}' || ip link | awk -F': ' '/^[0-9]+: [^lo]/{print $2; exit}')
  SERVER_IP=$(ip -4 addr show "$PRIMARY_IFACE" 2>/dev/null | awk '/inet /{split($2,a,"/"); print a[1]}' | head -1)
  NETWORK_PREFIX=$(ip -4 addr show "$PRIMARY_IFACE" 2>/dev/null | awk '/inet /{print $2}' | head -1 | cut -d'/' -f1 | awk -F. '{print $1"."$2"."$3}')

  [[ -n "$SERVER_IP" ]] || err "Could not detect server IP address. Check your network configuration."
  info "Network interface: $PRIMARY_IFACE"
  info "Server IP address: $SERVER_IP"
}

# ── Interactive configuration ─────────────────────────────────────────────────
configure_interactive() {
  step "Network Configuration"
  echo ""
  echo -e "  ${BOLD}Detected settings (press Enter to accept, or type new value):${NC}"
  echo ""

  read -rp "  PXE Server IP Address [$SERVER_IP]: " input
  SERVER_IP="${input:-$SERVER_IP}"

  read -rp "  Network Interface [$PRIMARY_IFACE]: " input
  PRIMARY_IFACE="${input:-$PRIMARY_IFACE}"

  # Suggest DHCP range based on server IP
  DHCP_START="${NETWORK_PREFIX}.100"
  DHCP_END="${NETWORK_PREFIX}.200"
  DHCP_NETMASK="255.255.255.0"
  DHCP_GATEWAY="$SERVER_IP"
  DHCP_DNS="$SERVER_IP"

  echo ""
  echo -e "  ${BOLD}DHCP Configuration:${NC}"
  read -rp "  DHCP Range Start [$DHCP_START]: " input
  DHCP_START="${input:-$DHCP_START}"

  read -rp "  DHCP Range End [$DHCP_END]: " input
  DHCP_END="${input:-$DHCP_END}"

  read -rp "  Subnet Mask [$DHCP_NETMASK]: " input
  DHCP_NETMASK="${input:-$DHCP_NETMASK}"

  read -rp "  Default Gateway [$DHCP_GATEWAY]: " input
  DHCP_GATEWAY="${input:-$DHCP_GATEWAY}"

  read -rp "  DNS Server [$DHCP_DNS]: " input
  DHCP_DNS="${input:-$DHCP_DNS}"

  echo ""
  echo -e "  ${BOLD}Web UI Port:${NC}"
  read -rp "  Management Web UI Port [$WEB_PORT]: " input
  WEB_PORT="${input:-$WEB_PORT}"

  echo ""
  echo -e "  ${BOLD}Summary of configuration:${NC}"
  echo -e "  ┌────────────────────────────────────────────┐"
  echo -e "  │  Server IP     : ${CYAN}$SERVER_IP${NC}"
  echo -e "  │  Interface     : ${CYAN}$PRIMARY_IFACE${NC}"
  echo -e "  │  DHCP Range    : ${CYAN}$DHCP_START - $DHCP_END${NC}"
  echo -e "  │  Netmask       : ${CYAN}$DHCP_NETMASK${NC}"
  echo -e "  │  Gateway       : ${CYAN}$DHCP_GATEWAY${NC}"
  echo -e "  │  DNS           : ${CYAN}$DHCP_DNS${NC}"
  echo -e "  │  Web UI Port   : ${CYAN}$WEB_PORT${NC}"
  echo -e "  └────────────────────────────────────────────┘"
  echo ""
  read -rp "  Proceed with installation? [Y/n]: " ans
  [[ "${ans,,}" != "n" ]] || exit 0
}

# ── Package installation ──────────────────────────────────────────────────────
install_packages() {
  step "Installing Required Packages"

  dnf install -y epel-release &>>"$LOG_FILE" || warn "EPEL already installed or unavailable"
  dnf install -y \
    dnsmasq nginx \
    python3 python3-pip python3-venv \
    gcc make perl xz-devel binutils \
    genisoimage isomd5sum \
    tftp-server \
    curl wget rsync \
    lsof net-tools \
    firewalld \
    &>>"$LOG_FILE" && log "Packages installed" || err "Package installation failed — check $LOG_FILE"
}

# ── iPXE build ────────────────────────────────────────────────────────────────
build_ipxe() {
  step "Building iPXE"

  IPXE_SRC_DIR=""
  # Find iPXE source in the same directory as this script
  for candidate in \
    "$SCRIPT_DIR/iPXE/ipxe-bd13697/src" \
    "$SCRIPT_DIR/../iPXE/ipxe-bd13697/src" \
    "/tmp/pxe_source/PXE-1.0.21/iPXE/ipxe-bd13697/src"; do
    if [[ -d "$candidate" && -f "$candidate/Makefile" ]]; then
      IPXE_SRC_DIR="$candidate"
      break
    fi
  done

  mkdir -p "$TFTP_DIR/ipxe"

  if [[ -z "$IPXE_SRC_DIR" ]]; then
    warn "iPXE source not found. Downloading pre-built binaries..."
    download_ipxe_binaries
    return
  fi

  info "Building iPXE from source at $IPXE_SRC_DIR"

  # Create embedded boot script
  cat > /tmp/lrn_pxe_boot.ipxe << IPXESCRIPT
#!ipxe
:retry
dhcp || goto retry
chain http://${SERVER_IP}:${WEB_PORT}/menu.ipxe || shell
IPXESCRIPT

  # Build BIOS image
  info "Building BIOS image (undionly.kpxe)..."
  make -C "$IPXE_SRC_DIR" bin/undionly.kpxe \
    EMBED=/tmp/lrn_pxe_boot.ipxe \
    -j"$(nproc)" &>>"$LOG_FILE" \
    && cp "$IPXE_SRC_DIR/bin/undionly.kpxe" "$TFTP_DIR/ipxe/" \
    && log "BIOS iPXE binary built" \
    || { warn "BIOS build failed, downloading fallback..."; download_ipxe_bios; }

  # Build UEFI image
  info "Building UEFI image (ipxe.efi)..."
  make -C "$IPXE_SRC_DIR" bin-x86_64-efi/ipxe.efi \
    EMBED=/tmp/lrn_pxe_boot.ipxe \
    -j"$(nproc)" &>>"$LOG_FILE" \
    && cp "$IPXE_SRC_DIR/bin-x86_64-efi/ipxe.efi" "$TFTP_DIR/ipxe/" \
    && log "UEFI iPXE binary built" \
    || { warn "UEFI build failed, downloading fallback..."; download_ipxe_uefi; }
}

download_ipxe_binaries() {
  download_ipxe_bios
  download_ipxe_uefi
}

download_ipxe_bios() {
  curl -sSL "https://boot.ipxe.org/undionly.kpxe" \
    -o "$TFTP_DIR/ipxe/undionly.kpxe" &>>"$LOG_FILE" \
    && log "Downloaded undionly.kpxe" \
    || err "Failed to download iPXE BIOS binary"
}

download_ipxe_uefi() {
  curl -sSL "https://boot.ipxe.org/ipxe.efi" \
    -o "$TFTP_DIR/ipxe/ipxe.efi" &>>"$LOG_FILE" \
    && log "Downloaded ipxe.efi" \
    || err "Failed to download iPXE UEFI binary"
}

# ── Directory structure ───────────────────────────────────────────────────────
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

  # Install web app files
  cp -r "$SCRIPT_DIR/web/"* "$INSTALL_DIR/web/" 2>/dev/null || true
  [[ -d "$SCRIPT_DIR/web" ]] && cp -r "$SCRIPT_DIR/web/." "$INSTALL_DIR/web/" &>>"$LOG_FILE"

  log "Directories created"
}

# ── Initial config files ──────────────────────────────────────────────────────
create_initial_config() {
  step "Creating Configuration Files"

  # menu.json — empty menu to start
  cat > "$INSTALL_DIR/config/menu.json" << JSON
{
  "title": "LRN_PXE Boot Menu",
  "timeout": 60,
  "default": "",
  "entries": []
}
JSON

  # settings.json
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
  "version": "1.0.0"
}
JSON

  log "Configuration files created"
}

# ── dnsmasq configuration ─────────────────────────────────────────────────────
configure_dnsmasq() {
  step "Configuring dnsmasq (DHCP + TFTP)"

  # Backup original config
  [[ -f /etc/dnsmasq.conf ]] && cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bak.$(date +%s)

  cat > /etc/dnsmasq.d/lrn_pxe.conf << DNSMASQ
# =============================================================================
# LRN_PXE - dnsmasq configuration
# Managed by LRN_PXE — do not edit manually
# =============================================================================

# Bind to PXE interface only
interface=${PRIMARY_IFACE}
bind-interfaces
except-interface=lo

# DHCP range and lease time
dhcp-range=${DHCP_START},${DHCP_END},${DHCP_NETMASK},${DHCP_LEASE_TIME:-12h}

# Default gateway and DNS
dhcp-option=option:router,${DHCP_GATEWAY}
dhcp-option=option:dns-server,${DHCP_DNS}

# TFTP server
enable-tftp
tftp-root=${TFTP_DIR}

# ── PXE Boot Logic ────────────────────────────────────────────────────────────
# Detect if client is already running iPXE (option 175 = iPXE)
dhcp-match=set:ipxe,175

# Detect UEFI client (arch = 7 or 9)
dhcp-match=set:efi-x86_64,option:client-arch,7
dhcp-match=set:efi-x86_64,option:client-arch,9

# Already running iPXE — chainload the menu script directly
dhcp-boot=tag:ipxe,http://${SERVER_IP}:${WEB_PORT}/menu.ipxe

# UEFI clients (not yet iPXE) — serve iPXE EFI binary
dhcp-boot=tag:efi-x86_64,tag:!ipxe,ipxe/ipxe.efi,pxeserver,${SERVER_IP}

# BIOS clients (not yet iPXE) — serve iPXE BIOS binary
dhcp-boot=tag:!efi-x86_64,tag:!ipxe,ipxe/undionly.kpxe,pxeserver,${SERVER_IP}

# PXE server address
dhcp-option=66,${SERVER_IP}

# Log DHCP transactions
log-dhcp
log-facility=/var/log/dnsmasq.log
DNSMASQ

  systemctl enable dnsmasq &>>"$LOG_FILE"
  systemctl restart dnsmasq &>>"$LOG_FILE" && log "dnsmasq configured and started" \
    || err "dnsmasq failed to start — check: journalctl -u dnsmasq"
}

# ── nginx configuration ───────────────────────────────────────────────────────
configure_nginx() {
  step "Configuring nginx (HTTP file server)"

  # Backup default config
  [[ -f /etc/nginx/nginx.conf ]] && cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak.$(date +%s)

  cat > /etc/nginx/conf.d/lrn_pxe.conf << NGINX
# =============================================================================
# LRN_PXE - nginx configuration
# Managed by LRN_PXE — do not edit manually
# =============================================================================

server {
    listen 80 default_server;
    server_name _;
    root ${INSTALL_DIR};
    access_log /var/log/nginx/lrn_pxe_access.log;
    error_log  /var/log/nginx/lrn_pxe_error.log;

    # ── Static ISO and boot file serving ─────────────────────────────────────
    location /isos/ {
        alias ${INSTALL_DIR}/isos/;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
    }

    location /boot/ {
        alias ${INSTALL_DIR}/boot/;
        autoindex on;
        autoindex_exact_size off;
    }

    location /kickstarts/ {
        alias ${INSTALL_DIR}/kickstarts/;
        autoindex on;
    }

    location /mounts/ {
        alias ${INSTALL_DIR}/mounts/;
        autoindex on;
        autoindex_exact_size off;
    }

    # ── Proxy everything else to Flask (Web UI + menu generation) ─────────────
    location / {
        proxy_pass         http://127.0.0.1:${WEB_PORT};
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
        client_max_body_size 50G;
    }
}
NGINX

  # Remove default server block if exists
  [[ -f /etc/nginx/conf.d/default.conf ]] && mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.disabled

  # Test config
  nginx -t &>>"$LOG_FILE" && log "nginx config valid" || err "nginx config invalid — check $LOG_FILE"

  systemctl enable nginx &>>"$LOG_FILE"
  systemctl restart nginx &>>"$LOG_FILE" && log "nginx configured and started" \
    || err "nginx failed to start"
}

# ── Python venv + Flask ───────────────────────────────────────────────────────
setup_python_app() {
  step "Setting Up Python Web Application"

  python3 -m venv "$INSTALL_DIR/venv" &>>"$LOG_FILE" && log "Python venv created"

  "$INSTALL_DIR/venv/bin/pip" install --upgrade pip &>>"$LOG_FILE"
  "$INSTALL_DIR/venv/bin/pip" install \
    flask flask-cors \
    &>>"$LOG_FILE" && log "Python packages installed"

  # Copy web app from repo
  if [[ -d "$SCRIPT_DIR/web" ]]; then
    cp -r "$SCRIPT_DIR/web/." "$INSTALL_DIR/web/" &>>"$LOG_FILE"
    log "Web application files installed"
  else
    err "Web application files not found at $SCRIPT_DIR/web"
  fi
}

# ── systemd service ───────────────────────────────────────────────────────────
install_service() {
  step "Installing systemd Service"

  cat > /etc/systemd/system/lrn-pxe.service << SYSTEMD
[Unit]
Description=LRN_PXE Web Management Interface
After=network.target nginx.service
Wants=nginx.service

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

  systemctl daemon-reload &>>"$LOG_FILE"
  systemctl enable lrn-pxe &>>"$LOG_FILE"
  systemctl start lrn-pxe &>>"$LOG_FILE" && log "LRN_PXE web service started" \
    || err "LRN_PXE web service failed to start — check: journalctl -u lrn-pxe"
}

# ── Firewall ──────────────────────────────────────────────────────────────────
configure_firewall() {
  step "Configuring Firewall"

  systemctl enable --now firewalld &>>"$LOG_FILE" 2>&1 || true

  firewall-cmd --permanent --add-service=dhcp   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-service=tftp   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-service=http   &>>"$LOG_FILE"
  firewall-cmd --permanent --add-port="${WEB_PORT}/tcp" &>>"$LOG_FILE"
  firewall-cmd --reload                          &>>"$LOG_FILE"

  log "Firewall rules applied"
}

# ── CLI tool ──────────────────────────────────────────────────────────────────
install_cli() {
  step "Installing CLI Tool"

  if [[ -f "$SCRIPT_DIR/scripts/lrn-pxe-cli.sh" ]]; then
    cp "$SCRIPT_DIR/scripts/lrn-pxe-cli.sh" /usr/local/bin/lrn-pxe
    chmod +x /usr/local/bin/lrn-pxe
    log "CLI tool installed at /usr/local/bin/lrn-pxe"
  fi
}

# ── SELinux ───────────────────────────────────────────────────────────────────
configure_selinux() {
  if command -v getenforce &>/dev/null && [[ "$(getenforce)" != "Disabled" ]]; then
    step "Configuring SELinux"
    setsebool -P httpd_can_network_connect 1 &>>"$LOG_FILE" || true
    setsebool -P httpd_read_user_content 1 &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/isos" &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/boot" &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/kickstarts" &>>"$LOG_FILE" || true
    chcon -Rt httpd_sys_content_t "$INSTALL_DIR/mounts" &>>"$LOG_FILE" || true
    log "SELinux contexts set"
  fi
}

# ── Final output ──────────────────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         LRN_PXE Installation Complete! ✓             ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}Access the Web Management UI:${NC}"
  echo -e "  ${CYAN}http://${SERVER_IP}/${NC}  (via nginx on port 80)"
  echo -e "  ${CYAN}http://${SERVER_IP}:${WEB_PORT}/${NC}  (Flask direct)"
  echo ""
  echo -e "  ${BOLD}Key Directories:${NC}"
  echo -e "  ${YELLOW}ISOs:${NC}           $INSTALL_DIR/isos/"
  echo -e "  ${YELLOW}Kickstarts:${NC}     $INSTALL_DIR/kickstarts/"
  echo -e "  ${YELLOW}Boot files:${NC}     $INSTALL_DIR/boot/"
  echo -e "  ${YELLOW}iPXE binaries:${NC}  $TFTP_DIR/ipxe/"
  echo ""
  echo -e "  ${BOLD}Service Management:${NC}"
  echo -e "  ${CYAN}systemctl status lrn-pxe${NC}    — Web UI status"
  echo -e "  ${CYAN}systemctl status dnsmasq${NC}     — DHCP/TFTP status"
  echo -e "  ${CYAN}systemctl status nginx${NC}       — HTTP server status"
  echo ""
  echo -e "  ${BOLD}CLI Tool:${NC}  ${CYAN}lrn-pxe --help${NC}"
  echo ""
  echo -e "  ${BOLD}Installation log:${NC}  $LOG_FILE"
  echo ""
  echo -e "  ${YELLOW}Next steps:${NC}"
  echo -e "  1. Open ${CYAN}http://${SERVER_IP}/${NC} in your browser"
  echo -e "  2. Click ${BOLD}Add Image${NC} to upload an ISO file"
  echo -e "  3. Optionally add a Kickstart file for automated installs"
  echo -e "  4. Boot a network client and watch it appear in the menu"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  touch "$LOG_FILE"
  clear
  banner

  check_root
  check_os
  detect_network
  configure_interactive

  log "Starting installation — logging to $LOG_FILE"

  install_packages
  build_ipxe
  create_directories
  create_initial_config
  setup_python_app
  configure_dnsmasq
  configure_nginx
  install_service
  configure_firewall
  configure_selinux
  install_cli
  print_summary
}

main "$@"
