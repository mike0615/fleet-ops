#!/usr/bin/env bash
# =============================================================================
# LRN_PXE — Offline Bundle Fetcher
# Run this script on an INTERNET-CONNECTED Rocky Linux 9 or 10 machine.
# It downloads all RPMs, Python wheels, iPXE binaries, and frontend assets
# needed for an airgapped installation.
#
# Output: bundle/ directory (alongside this script)
# Next step: run create-airgap-package.sh to produce a distributable tarball
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$SCRIPT_DIR/bundle"

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
step() { echo -e "\n${BOLD}${CYAN}── $* ──${NC}"; }

# ── Versions ─────────────────────────────────────────────────────────────────
BOOTSTRAP_VERSION="5.3.3"
BOOTSTRAP_ICONS_VERSION="1.11.3"
IPXE_BIOS_URL="https://boot.ipxe.org/undionly.kpxe"
IPXE_EFI_URL="https://boot.ipxe.org/ipxe.efi"

# ── Required RPM packages ─────────────────────────────────────────────────────
RPM_PACKAGES=(
  dnsmasq
  nginx
  python3
  python3-pip
  python3-devel
  gcc
  make
  perl
  perl-Data-Dumper
  perl-Digest-MD5
  perl-File-Spec
  xz-devel
  binutils
  genisoimage
  isomd5sum
  curl
  wget
  rsync
  lsof
  net-tools
  firewalld
  openssl-devel
)

# ── Python packages ───────────────────────────────────────────────────────────
PIP_PACKAGES=(
  "flask==3.1.3"
  "flask-cors==6.0.2"
)

# ── Pre-flight ────────────────────────────────────────────────────────────────
check_root() {
  [[ $EUID -eq 0 ]] || err "Run as root: sudo bash fetch-bundle.sh"
}

check_os() {
  source /etc/os-release 2>/dev/null || err "Cannot detect OS"
  if [[ "$ID" != "rocky" ]]; then
    warn "Detected: $PRETTY_NAME (designed for Rocky Linux 9/10)"
    read -rp "Continue anyway? [y/N]: " ans
    [[ "${ans,,}" == "y" ]] || exit 0
  fi
  info "OS: $PRETTY_NAME"
}

check_internet() {
  curl -s --max-time 5 https://cdn.jsdelivr.net >/dev/null 2>&1 \
    || err "No internet connection. This script requires internet access."
  log "Internet connectivity confirmed"
}

# ── Create bundle directory structure ─────────────────────────────────────────
create_dirs() {
  step "Creating bundle directory"
  mkdir -p \
    "$BUNDLE_DIR/rpms" \
    "$BUNDLE_DIR/pip-wheels" \
    "$BUNDLE_DIR/ipxe" \
    "$BUNDLE_DIR/vendor"
  log "Bundle directory: $BUNDLE_DIR"
}

# ── Download RPMs ─────────────────────────────────────────────────────────────
download_rpms() {
  step "Downloading RPM packages"

  # Enable EPEL first
  info "Enabling EPEL repository..."
  dnf install -y epel-release &>/dev/null || warn "EPEL may already be installed"
  dnf makecache &>/dev/null

  info "Downloading RPMs and all dependencies..."
  dnf download \
    --resolve \
    --alldeps \
    --destdir="$BUNDLE_DIR/rpms" \
    "${RPM_PACKAGES[@]}" \
    2>&1 | grep -E "^(Downloading|Complete)" | head -50 || true

  # Count what we got
  RPM_COUNT=$(ls "$BUNDLE_DIR/rpms/"*.rpm 2>/dev/null | wc -l)
  log "Downloaded $RPM_COUNT RPM packages"

  # Also save the EPEL release RPM
  info "Downloading EPEL release RPM..."
  dnf download --destdir="$BUNDLE_DIR/rpms" epel-release &>/dev/null || true

  # Create a local repo metadata for the bundle
  info "Creating local repo metadata..."
  if command -v createrepo_c &>/dev/null; then
    createrepo_c "$BUNDLE_DIR/rpms/" &>/dev/null && log "Repo metadata created"
  elif command -v createrepo &>/dev/null; then
    createrepo "$BUNDLE_DIR/rpms/" &>/dev/null && log "Repo metadata created"
  else
    warn "createrepo not found — installing..."
    dnf install -y createrepo_c &>/dev/null && \
    createrepo_c "$BUNDLE_DIR/rpms/" &>/dev/null && log "Repo metadata created"
  fi
}

# ── Download Python wheels ────────────────────────────────────────────────────
download_pip_wheels() {
  step "Downloading Python wheels"

  python3 -m pip download \
    --dest "$BUNDLE_DIR/pip-wheels" \
    --python-version 3.9 \
    --only-binary :none: \
    --no-binary :none: \
    "${PIP_PACKAGES[@]}" \
    2>/dev/null || true

  # Prefer binary wheels (faster install)
  python3 -m pip download \
    --dest "$BUNDLE_DIR/pip-wheels" \
    "${PIP_PACKAGES[@]}" \
    &>/dev/null

  WHEEL_COUNT=$(ls "$BUNDLE_DIR/pip-wheels/"* 2>/dev/null | wc -l)
  log "Downloaded $WHEEL_COUNT Python packages/wheels"
}

# ── Download pre-built iPXE binaries ─────────────────────────────────────────
download_ipxe() {
  step "Downloading pre-built iPXE binaries"
  info "These are fallback binaries — the installer will try to build from source first."

  curl -sSL "$IPXE_BIOS_URL" -o "$BUNDLE_DIR/ipxe/undionly.kpxe" \
    && log "Downloaded undionly.kpxe (BIOS)" \
    || warn "Failed to download undionly.kpxe"

  curl -sSL "$IPXE_EFI_URL" -o "$BUNDLE_DIR/ipxe/ipxe.efi" \
    && log "Downloaded ipxe.efi (UEFI)" \
    || warn "Failed to download ipxe.efi"

  ls -lh "$BUNDLE_DIR/ipxe/"
}

# ── Download Bootstrap & Icons (frontend assets) ──────────────────────────────
download_frontend_assets() {
  step "Downloading frontend assets (Bootstrap + Bootstrap Icons)"

  VENDOR="$BUNDLE_DIR/vendor"

  # Bootstrap CSS
  info "Bootstrap $BOOTSTRAP_VERSION CSS..."
  curl -sSL \
    "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/css/bootstrap.min.css" \
    -o "$VENDOR/bootstrap.min.css" \
    && log "bootstrap.min.css" || warn "Failed"

  # Bootstrap JS bundle (includes Popper)
  info "Bootstrap $BOOTSTRAP_VERSION JS bundle..."
  curl -sSL \
    "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/js/bootstrap.bundle.min.js" \
    -o "$VENDOR/bootstrap.bundle.min.js" \
    && log "bootstrap.bundle.min.js" || warn "Failed"

  # Bootstrap Icons CSS
  info "Bootstrap Icons $BOOTSTRAP_ICONS_VERSION CSS..."
  curl -sSL \
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@${BOOTSTRAP_ICONS_VERSION}/font/bootstrap-icons.min.css" \
    -o "$VENDOR/bootstrap-icons.min.css" \
    && log "bootstrap-icons.min.css" || warn "Failed"

  # Bootstrap Icons fonts (woff2 — referenced by the CSS)
  mkdir -p "$VENDOR/fonts"
  info "Bootstrap Icons font files..."

  # Extract font filenames from the CSS and download them
  for font_file in bootstrap-icons.woff2 bootstrap-icons.woff; do
    curl -sSL \
      "https://cdn.jsdelivr.net/npm/bootstrap-icons@${BOOTSTRAP_ICONS_VERSION}/font/fonts/${font_file}" \
      -o "$VENDOR/fonts/${font_file}" \
      && log "fonts/${font_file}" || warn "Failed: fonts/${font_file}"
  done

  # Fix the font path in the CSS to point to ./fonts/ (relative)
  sed -i 's|../fonts/|./fonts/|g' "$VENDOR/bootstrap-icons.min.css" \
    && log "Font paths patched in CSS" || warn "Font path patch failed"

  log "All frontend assets downloaded"
}

# ── Write bundle manifest ─────────────────────────────────────────────────────
write_manifest() {
  step "Writing bundle manifest"
  cat > "$BUNDLE_DIR/MANIFEST.txt" << MANIFEST
LRN_PXE Offline Bundle Manifest
================================
Generated  : $(date -u '+%Y-%m-%d %H:%M:%S UTC')
Host OS    : $(source /etc/os-release && echo "$PRETTY_NAME")
Arch       : $(uname -m)

Bootstrap  : ${BOOTSTRAP_VERSION}
BS Icons   : ${BOOTSTRAP_ICONS_VERSION}

RPM count  : $(ls "$BUNDLE_DIR/rpms/"*.rpm 2>/dev/null | wc -l)
Wheel count: $(ls "$BUNDLE_DIR/pip-wheels/"* 2>/dev/null | wc -l)
iPXE BIOS  : $([ -f "$BUNDLE_DIR/ipxe/undionly.kpxe" ] && echo "present" || echo "MISSING")
iPXE UEFI  : $([ -f "$BUNDLE_DIR/ipxe/ipxe.efi" ] && echo "present" || echo "MISSING")
Bootstrap  : $([ -f "$BUNDLE_DIR/vendor/bootstrap.min.css" ] && echo "present" || echo "MISSING")
BS Icons   : $([ -f "$BUNDLE_DIR/vendor/bootstrap-icons.min.css" ] && echo "present" || echo "MISSING")
MANIFEST
  cat "$BUNDLE_DIR/MANIFEST.txt"
  log "Manifest written to $BUNDLE_DIR/MANIFEST.txt"
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
  BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" 2>/dev/null | cut -f1)
  echo ""
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         Bundle Download Complete! ✓          ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  Bundle size : ${CYAN}${BUNDLE_SIZE}${NC}"
  echo -e "  Location    : ${CYAN}${BUNDLE_DIR}${NC}"
  echo ""
  echo -e "  ${BOLD}Next step:${NC}"
  echo -e "  Run ${CYAN}sudo bash create-airgap-package.sh${NC}"
  echo -e "  to create a distributable .tar.gz for your airgapped machines."
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  clear
  echo -e "${BOLD}${CYAN}  LRN_PXE — Offline Bundle Fetcher${NC}"
  echo -e "  Downloading all dependencies for airgapped installation"
  echo -e "  ─────────────────────────────────────────────────────────"
  echo ""

  check_root
  check_os
  check_internet
  create_dirs
  download_rpms
  download_pip_wheels
  download_ipxe
  download_frontend_assets
  write_manifest
  print_summary
}

main "$@"
