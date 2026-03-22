#!/usr/bin/env bash
# =============================================================================
# LRN_PXE — Airgap Package Creator
# Run this on the SAME internet-connected machine after fetch-bundle.sh.
# Produces a single .tar.gz ready to transfer to airgapped targets.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="1.0.0"
PACKAGE_NAME="lrn_pxe_offline_v${VERSION}"
OUTPUT_DIR="${SCRIPT_DIR}/.."   # One level up — keeps the tarball out of the source tree
BUNDLE_DIR="$SCRIPT_DIR/bundle"

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo -e "\n${BOLD}${CYAN}  LRN_PXE — Airgap Package Creator${NC}\n"

# ── Validate bundle exists ────────────────────────────────────────────────────
[[ -d "$BUNDLE_DIR" ]] \
  || err "bundle/ not found. Run 'sudo bash fetch-bundle.sh' first."

[[ -f "$BUNDLE_DIR/MANIFEST.txt" ]] \
  || err "bundle/MANIFEST.txt missing. Re-run fetch-bundle.sh."

RPM_COUNT=$(ls "$BUNDLE_DIR/rpms/"*.rpm 2>/dev/null | wc -l)
[[ $RPM_COUNT -gt 0 ]] || err "No RPMs in bundle/rpms/. Re-run fetch-bundle.sh."

info "Bundle validation passed ($RPM_COUNT RPMs found)"

# ── Build the package structure ───────────────────────────────────────────────
STAGING_DIR="/tmp/${PACKAGE_NAME}"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

info "Staging package at $STAGING_DIR ..."

# Copy the full lrn_pxe source (minus git and temp files)
rsync -a \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.DS_Store' \
  --exclude='bundle/'          \
  "$SCRIPT_DIR/" "$STAGING_DIR/lrn_pxe/"

# Copy the bundle into the package
cp -r "$BUNDLE_DIR" "$STAGING_DIR/lrn_pxe/bundle"

# Set execute permissions on shell scripts
find "$STAGING_DIR" -name "*.sh" -exec chmod +x {} \;

# ── Add a top-level README ────────────────────────────────────────────────────
cat > "$STAGING_DIR/README-AIRGAP.txt" << README
LRN_PXE Offline Installation Package
=====================================
Version  : ${VERSION}
Contents : lrn_pxe/ directory with bundled dependencies

QUICK START
-----------
1. Transfer this package to your Rocky Linux 9/10 server (e.g. via SCP or USB):
     scp lrn_pxe_offline_v${VERSION}.tar.gz admin@192.168.1.10:/tmp/

2. On the target server, extract and run the installer:
     cd /tmp
     tar -xzf lrn_pxe_offline_v${VERSION}.tar.gz
     cd lrn_pxe_offline_v${VERSION}
     sudo bash lrn_pxe/install-offline.sh

3. When prompted, enter your network details (or press Enter for auto-detected defaults).

4. Access the web interface at:
     http://<your-server-ip>/

NO INTERNET REQUIRED on the target machine.

See lrn_pxe/docs/USER_GUIDE.md for full documentation.
See lrn_pxe/docs/AIRGAP_INSTALL.md for detailed offline install instructions.

BUNDLE MANIFEST
---------------
$(cat "$BUNDLE_DIR/MANIFEST.txt")
README

log "Top-level README written"

# ── Create tarball ────────────────────────────────────────────────────────────
TARBALL="${OUTPUT_DIR}/${PACKAGE_NAME}.tar.gz"
info "Creating tarball: $(basename "$TARBALL") ..."

tar -czf "$TARBALL" -C "/tmp" "$PACKAGE_NAME"

TARBALL_SIZE=$(du -sh "$TARBALL" | cut -f1)
log "Package created: $(realpath "$TARBALL") (${TARBALL_SIZE})"

# ── Checksum ──────────────────────────────────────────────────────────────────
sha256sum "$TARBALL" > "${TARBALL}.sha256"
log "SHA256: $(cat "${TARBALL}.sha256" | awk '{print $1}')"

# ── Cleanup staging ───────────────────────────────────────────────────────────
rm -rf "$STAGING_DIR"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}+======================================================+${NC}"
echo -e "${GREEN}${BOLD}|       Airgap Package Ready!  ✓                      |${NC}"
echo -e "${GREEN}${BOLD}+======================================================+${NC}"
echo ""
echo -e "  ${BOLD}Package:${NC}  $(realpath "$TARBALL")"
echo -e "  ${BOLD}Size:${NC}     ${TARBALL_SIZE}"
echo -e "  ${BOLD}SHA256:${NC}   $(cat "${TARBALL}.sha256" | awk '{print $1}' | head -c 24)..."
echo ""
echo -e "  ${BOLD}Transfer to target machine:${NC}"
echo -e "  ${CYAN}scp $(basename "$TARBALL") admin@TARGET_IP:/tmp/${NC}"
echo ""
echo -e "  ${BOLD}Install on target (no internet needed):${NC}"
echo -e "  ${CYAN}cd /tmp && tar -xzf $(basename "$TARBALL")${NC}"
echo -e "  ${CYAN}cd ${PACKAGE_NAME} && sudo bash lrn_pxe/install-offline.sh${NC}"
echo ""
