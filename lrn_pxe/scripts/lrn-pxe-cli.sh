#!/usr/bin/env bash
# =============================================================================
# LRN_PXE CLI Management Tool
# Usage: lrn-pxe <command> [options]
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

BASE_DIR="/opt/lrn_pxe"
WEB_PORT=$(python3 -c "import json; d=json.load(open('$BASE_DIR/config/settings.json')); print(d.get('web_port',8080))" 2>/dev/null || echo "8080")

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

usage() {
  cat << EOF
${BOLD}LRN_PXE Management Tool${NC}

${BOLD}USAGE:${NC}
  lrn-pxe <command> [options]

${BOLD}COMMANDS:${NC}
  ${CYAN}status${NC}                   Show status of all services
  ${CYAN}start${NC}                    Start all LRN_PXE services
  ${CYAN}stop${NC}                     Stop all LRN_PXE services
  ${CYAN}restart${NC}                  Restart all LRN_PXE services
  ${CYAN}logs${NC} [service]           Tail logs (web|dhcp|http, default: web)

  ${CYAN}add-iso${NC} <path>           Add and process an ISO file
  ${CYAN}list-isos${NC}                List all registered ISO images
  ${CYAN}remove-iso${NC} <id>          Remove an ISO and its boot files

  ${CYAN}add-kickstart${NC} <path>     Copy a kickstart file into the server
  ${CYAN}list-kickstarts${NC}          List all kickstart files
  ${CYAN}edit-kickstart${NC} <name>    Edit a kickstart file in \$EDITOR

  ${CYAN}menu-show${NC}                Display the current iPXE menu script
  ${CYAN}menu-enable${NC} <id>         Enable a menu entry
  ${CYAN}menu-disable${NC} <id>        Disable a menu entry

  ${CYAN}build-ipxe${NC}               Rebuild iPXE binaries from source
  ${CYAN}update-dhcp${NC}              Apply current DHCP settings and restart dnsmasq

  ${CYAN}info${NC}                     Show server configuration summary
  ${CYAN}version${NC}                  Show version information

${BOLD}EXAMPLES:${NC}
  lrn-pxe add-iso /mnt/usb/Rocky-9.4-x86_64-dvd.iso
  lrn-pxe add-kickstart /home/admin/rocky9.ks
  lrn-pxe menu-enable rocky9-auto
  lrn-pxe logs dhcp

EOF
}

# ── Service helpers ───────────────────────────────────────────────────────────
cmd_status() {
  echo -e "\n${BOLD}LRN_PXE Service Status${NC}\n"
  for svc in lrn-pxe dnsmasq nginx; do
    status=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
    color=$( [[ "$status" == "active" ]] && echo "$GREEN" || echo "$RED" )
    label=$( [[ "$svc" == "lrn-pxe" ]] && echo "Web Interface" \
          || [[ "$svc" == "dnsmasq" ]] && echo "DHCP / TFTP  " \
          || echo "HTTP Server  " )
    echo -e "  ${label}  (${svc})   ${color}${status}${NC}"
  done
  echo ""
  # Disk usage
  df -h "$BASE_DIR" | awk 'NR==2{printf "  Disk: %s used of %s (%s free)\n", $3, $2, $4}'
  echo ""
}

cmd_start()   { systemctl start   lrn-pxe dnsmasq nginx; ok "All services started"; }
cmd_stop()    { systemctl stop    lrn-pxe dnsmasq nginx; ok "All services stopped"; }
cmd_restart() { systemctl restart lrn-pxe dnsmasq nginx; ok "All services restarted"; }

cmd_logs() {
  case "${1:-web}" in
    web)  journalctl -u lrn-pxe  -f --no-pager ;;
    dhcp) tail -f /var/log/dnsmasq.log ;;
    http) tail -f /var/log/nginx/lrn_pxe_access.log ;;
    *)    err "Unknown service. Use: web | dhcp | http" ;;
  esac
}

# ── ISO management ────────────────────────────────────────────────────────────
cmd_add_iso() {
  local src="${1:-}"
  [[ -n "$src" ]] || err "Usage: lrn-pxe add-iso <path-to.iso>"
  [[ -f "$src" ]] || err "File not found: $src"

  local filename=$(basename "$src")
  local iso_id="${filename%.iso}"
  local dest="$BASE_DIR/isos/$filename"

  info "Copying $filename to $BASE_DIR/isos/ ..."
  cp "$src" "$dest"
  ok "ISO copied"

  info "Extracting boot files..."
  local mount_path="$BASE_DIR/mounts/$iso_id"
  local boot_path="$BASE_DIR/boot/$iso_id"
  mkdir -p "$mount_path" "$boot_path"

  mount -o loop,ro "$dest" "$mount_path" 2>/dev/null || {
    warn "Loop mount failed — trying direct copy..."
    cp -r "$dest" "$mount_path/"
  }

  # Detect and extract boot files
  if [[ -f "$mount_path/images/pxeboot/vmlinuz" ]]; then
    cp "$mount_path/images/pxeboot/vmlinuz"   "$boot_path/vmlinuz"
    cp "$mount_path/images/pxeboot/initrd.img" "$boot_path/initrd.img"
    ok "Extracted RHEL-style boot files"
  elif [[ -f "$mount_path/casper/vmlinuz" ]]; then
    cp "$mount_path/casper/vmlinuz" "$boot_path/vmlinuz"
    cp "$mount_path/casper/initrd"  "$boot_path/initrd"
    ok "Extracted Ubuntu-style boot files"
  elif [[ -f "$mount_path/isolinux/vmlinuz" ]]; then
    cp "$mount_path/isolinux/vmlinuz"   "$boot_path/vmlinuz"
    cp "$mount_path/isolinux/initrd.img" "$boot_path/initrd.img"
    ok "Extracted isolinux boot files"
  else
    warn "Could not auto-detect boot files. Mount the ISO and extract manually."
    warn "Mount path: $mount_path"
  fi

  # Register in menu.json via API
  curl -sX POST "http://localhost:${WEB_PORT}/api/menu/entries" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"$iso_id\",\"iso_id\":\"$iso_id\",\"label\":\"$iso_id\",\"os_type\":\"rhel\",\"kickstart\":\"\",\"kernel_args\":\"\",\"enabled\":true}" \
    &>/dev/null && ok "Registered in menu (disabled by default)"

  echo ""
  echo -e "  ${BOLD}Next steps:${NC}"
  echo -e "  1. Open ${CYAN}http://$(hostname -I | awk '{print $1}')/images${NC}"
  echo -e "  2. Or run: ${CYAN}lrn-pxe menu-enable $iso_id${NC}"
}

cmd_list_isos() {
  echo -e "\n${BOLD}Registered Boot Images${NC}\n"
  printf "  %-40s %-10s %-8s\n" "Filename" "Size" "Boot"
  echo "  ────────────────────────────────────────────────────────────"
  for f in "$BASE_DIR/isos/"*.iso; do
    [[ -f "$f" ]] || { echo "  (none)"; break; }
    name=$(basename "$f")
    id="${name%.iso}"
    size=$(du -sh "$f" 2>/dev/null | cut -f1)
    boot=$( [[ -d "$BASE_DIR/boot/$id" ]] && echo "yes" || echo "no" )
    printf "  %-40s %-10s %-8s\n" "$name" "$size" "$boot"
  done
  echo ""
}

cmd_remove_iso() {
  local id="${1:-}"
  [[ -n "$id" ]] || err "Usage: lrn-pxe remove-iso <id>"
  read -rp "Remove $id and all associated files? [y/N]: " ans
  [[ "${ans,,}" == "y" ]] || exit 0

  rm -f "$BASE_DIR/isos/$id.iso"
  rm -rf "$BASE_DIR/boot/$id"
  umount -f "$BASE_DIR/mounts/$id" 2>/dev/null || true
  rm -rf "$BASE_DIR/mounts/$id"

  # Remove from menu via API
  curl -sX DELETE "http://localhost:${WEB_PORT}/api/images/$id" &>/dev/null

  ok "Removed $id"
}

# ── Kickstart management ──────────────────────────────────────────────────────
cmd_add_kickstart() {
  local src="${1:-}"
  [[ -n "$src" ]] || err "Usage: lrn-pxe add-kickstart <path>"
  [[ -f "$src" ]] || err "File not found: $src"
  cp "$src" "$BASE_DIR/kickstarts/"
  ok "Kickstart added: $(basename "$src")"
  info "URL: http://$(hostname -I | awk '{print $1}')/kickstarts/$(basename "$src")"
}

cmd_list_kickstarts() {
  echo -e "\n${BOLD}Kickstart Files${NC}\n"
  ls -lh "$BASE_DIR/kickstarts/" 2>/dev/null | grep -v '^total' \
    | awk '{printf "  %-30s %s\n", $NF, $5}' \
    || echo "  (none)"
  echo ""
}

cmd_edit_kickstart() {
  local name="${1:-}"
  [[ -n "$name" ]] || err "Usage: lrn-pxe edit-kickstart <filename>"
  local path="$BASE_DIR/kickstarts/$name"
  [[ -f "$path" ]] || err "Not found: $path"
  "${EDITOR:-vi}" "$path"
}

# ── Menu management ───────────────────────────────────────────────────────────
cmd_menu_show() {
  curl -s "http://localhost:${WEB_PORT}/menu.ipxe"
}

cmd_menu_enable() {
  local id="${1:-}"
  [[ -n "$id" ]] || err "Usage: lrn-pxe menu-enable <entry-id>"
  curl -sX PUT "http://localhost:${WEB_PORT}/api/menu/entries/$id" \
    -H "Content-Type: application/json" -d '{"enabled":true}' | grep -q "success" \
    && ok "Entry '$id' enabled" || err "Entry '$id' not found"
}

cmd_menu_disable() {
  local id="${1:-}"
  [[ -n "$id" ]] || err "Usage: lrn-pxe menu-disable <entry-id>"
  curl -sX PUT "http://localhost:${WEB_PORT}/api/menu/entries/$id" \
    -H "Content-Type: application/json" -d '{"enabled":false}' | grep -q "success" \
    && ok "Entry '$id' disabled" || err "Entry '$id' not found"
}

# ── Build iPXE ────────────────────────────────────────────────────────────────
cmd_build_ipxe() {
  TFTP_DIR="/var/lib/tftpboot"
  SERVER_IP=$(python3 -c "import json; d=json.load(open('$BASE_DIR/config/settings.json')); print(d['server_ip'])" 2>/dev/null || hostname -I | awk '{print $1}')
  PORT=$(python3 -c "import json; d=json.load(open('$BASE_DIR/config/settings.json')); print(d.get('web_port',8080))" 2>/dev/null || echo "8080")

  IPXE_SRC=""
  for candidate in /opt/lrn_pxe/ipxe-src/src /tmp/pxe_source/PXE-1.0.21/iPXE/ipxe-bd13697/src; do
    [[ -d "$candidate" ]] && IPXE_SRC="$candidate" && break
  done
  [[ -n "$IPXE_SRC" ]] || err "iPXE source not found. Place source at /opt/lrn_pxe/ipxe-src/"

  cat > /tmp/lrn_pxe_boot.ipxe << SCRIPT
#!ipxe
:retry
dhcp || goto retry
chain http://${SERVER_IP}:${PORT}/menu.ipxe || shell
SCRIPT

  info "Building BIOS image..."
  make -C "$IPXE_SRC" bin/undionly.kpxe EMBED=/tmp/lrn_pxe_boot.ipxe -j"$(nproc)" \
    && cp "$IPXE_SRC/bin/undionly.kpxe" "$TFTP_DIR/ipxe/" && ok "undionly.kpxe built"

  info "Building UEFI image..."
  make -C "$IPXE_SRC" bin-x86_64-efi/ipxe.efi EMBED=/tmp/lrn_pxe_boot.ipxe -j"$(nproc)" \
    && cp "$IPXE_SRC/bin-x86_64-efi/ipxe.efi" "$TFTP_DIR/ipxe/" && ok "ipxe.efi built"

  ok "iPXE build complete"
}

# ── Update DHCP config ────────────────────────────────────────────────────────
cmd_update_dhcp() {
  info "Regenerating dnsmasq config from settings..."
  SERVER_IP=$(python3 -c "import json; d=json.load(open('$BASE_DIR/config/settings.json')); print(d['server_ip'])" 2>/dev/null)
  # Re-run the relevant part of install.sh logic
  systemctl restart dnsmasq && ok "dnsmasq restarted with current settings"
}

# ── Info ──────────────────────────────────────────────────────────────────────
cmd_info() {
  local cfg="$BASE_DIR/config/settings.json"
  echo -e "\n${BOLD}LRN_PXE Configuration${NC}\n"
  if command -v python3 &>/dev/null && [[ -f "$cfg" ]]; then
    python3 -c "
import json
d = json.load(open('$cfg'))
fields = [
  ('Server IP',      'server_ip'),
  ('Web UI Port',    'web_port'),
  ('DHCP Interface', 'dhcp_interface'),
  ('DHCP Range',     None),
  ('Netmask',        'dhcp_netmask'),
  ('Gateway',        'dhcp_gateway'),
  ('DNS Server',     'dhcp_dns'),
  ('Lease Time',     'dhcp_lease_time'),
]
for label, key in fields:
    if key:
        print(f'  {label:<20} {d.get(key,\"N/A\")}')
    else:
        print(f'  {\"DHCP Range\":<20} {d.get(\"dhcp_start\",\"?\")} - {d.get(\"dhcp_end\",\"?\")}')
"
  fi
  echo ""
  echo -e "  ${BOLD}Key URLs:${NC}"
  SERVER_IP=$(python3 -c "import json; d=json.load(open('$cfg')); print(d.get('server_ip',''))" 2>/dev/null || hostname -I | awk '{print $1}')
  echo -e "  Web UI       http://${SERVER_IP}/"
  echo -e "  iPXE Menu    http://${SERVER_IP}/menu.ipxe"
  echo -e "  ISO files    http://${SERVER_IP}/isos/"
  echo -e "  Kickstarts   http://${SERVER_IP}/kickstarts/"
  echo ""
  echo -e "  ${BOLD}File paths:${NC}"
  echo -e "  ISOs         $BASE_DIR/isos/"
  echo -e "  Kickstarts   $BASE_DIR/kickstarts/"
  echo -e "  Boot files   $BASE_DIR/boot/"
  echo -e "  TFTP root    /var/lib/tftpboot/ipxe/"
  echo ""
}

cmd_version() {
  echo "LRN_PXE v1.0.0 — Rocky Linux 9/10 PXE Boot Server"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
  status)          cmd_status ;;
  start)           cmd_start ;;
  stop)            cmd_stop ;;
  restart)         cmd_restart ;;
  logs)            cmd_logs "${2:-web}" ;;
  add-iso)         cmd_add_iso "${2:-}" ;;
  list-isos)       cmd_list_isos ;;
  remove-iso)      cmd_remove_iso "${2:-}" ;;
  add-kickstart)   cmd_add_kickstart "${2:-}" ;;
  list-kickstarts) cmd_list_kickstarts ;;
  edit-kickstart)  cmd_edit_kickstart "${2:-}" ;;
  menu-show)       cmd_menu_show ;;
  menu-enable)     cmd_menu_enable "${2:-}" ;;
  menu-disable)    cmd_menu_disable "${2:-}" ;;
  build-ipxe)      cmd_build_ipxe ;;
  update-dhcp)     cmd_update_dhcp ;;
  info)            cmd_info ;;
  version)         cmd_version ;;
  help|--help|-h)  usage ;;
  *)               err "Unknown command: ${1}. Run 'lrn-pxe help' for usage." ;;
esac
