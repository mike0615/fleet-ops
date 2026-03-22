#!/bin/bash
# =============================================================================
# mac-ops — Airgap Preparation Script
# =============================================================================
# Author  : Mike Anderson
# Version : 1.2.0
# License : MIT
#
# Run this script on a CONNECTED machine (same OS/arch as your airgapped target)
# BEFORE transferring the package to the airgapped environment.
#
# What it does:
#   - Downloads all required pip wheel files into ./pip-packages/
#   - These are bundled into the package for offline installation
#
# Packages bundled:
#   flask, flask-cors, flask-socketio (SSH console WebSocket support)
#   apscheduler (cron scheduling), pyyaml, paramiko (SSH console)
#   ansible-core
#
# Usage:
#   bash prep-airgap.sh
#
# Then transfer the whole mac-ops/ directory to your airgapped machine and run:
#   sudo bash install.sh --airgap
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; CYN='\033[0;36m'; BLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${GRN}[✓]${NC} $*"; }
warn() { echo -e "${YLW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="${SRC}/pip-packages"

echo -e "${BLD}${CYN}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   mac-ops Airgap Package Preparation      ║"
echo "  ║   Author: Mike Anderson · v1.2.0          ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# Verify we have pip
command -v pip3 &>/dev/null || die "pip3 not found. Install python3-pip first."
command -v python3 &>/dev/null || die "python3 not found."

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ARCH=$(python3 -c "import platform; print(platform.machine())")
log "Python ${PYVER} on ${ARCH}"

# Create output directory
mkdir -p "$PKG_DIR"
warn "Downloading pip wheels to: ${PKG_DIR}"
warn "This may take 2-5 minutes..."

# Download all required packages and their dependencies as wheels
pip3 download \
    "flask>=3.0,<4" \
    "flask-cors>=4.0" \
    "flask-socketio>=5.3,<6" \
    "apscheduler>=3.10,<4" \
    "pyyaml>=6.0" \
    "paramiko>=3.0" \
    "ansible-core>=2.15" \
    --dest "$PKG_DIR" \
    --quiet

WHEEL_COUNT=$(ls "$PKG_DIR"/*.whl 2>/dev/null | wc -l)
TAR_COUNT=$(ls "$PKG_DIR"/*.tar.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$PKG_DIR" | cut -f1)

log "Downloaded ${WHEEL_COUNT} wheels + ${TAR_COUNT} source packages (${TOTAL_SIZE} total)"
echo ""
log "Package list:"
ls "$PKG_DIR" | while read f; do echo "    ${f}"; done

echo ""
log "Airgap preparation complete!"
echo ""
echo -e "${BLD}Next steps:${NC}"
echo "  1. Transfer the entire mac-ops/ folder (including pip-packages/) to your airgapped machine"
echo "  2. Run: sudo bash install.sh --airgap"
echo ""
echo -e "${YLW}Important: Download on the same OS and CPU architecture as your target machine${NC}"
echo -e "  This machine: Rocky Linux / ${ARCH} / Python ${PYVER}"
