#!/bin/bash
# MT7603U USB WiFi Driver - DKMS Install
# Automatically rebuilds driver on kernel updates
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DKMS_SRC_DIR="${SCRIPT_DIR}/dkms"
DKMS_NAME="mt7603usta"
DKMS_VER="1.14"
DKMS_DST="/usr/src/${DKMS_NAME}-${DKMS_VER}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[ "$EUID" -ne 0 ] && error "Please run with sudo: sudo bash dkms-install.sh"
[ ! -d "$DKMS_SRC_DIR" ] && error "dkms/ source directory not found"

# Install dependencies
info "Installing dependencies..."
apt-get update -qq
apt-get install -y dkms build-essential "linux-headers-$(uname -r)"

# Install firmware
info "Installing firmware..."
cp -f "${DKMS_SRC_DIR}/firmware/MT7603USTA.dat" /lib/firmware/
cp -f "${DKMS_SRC_DIR}/firmware/mt7603_e2.bin" /lib/firmware/

# Remove old DKMS if exists
if dkms status "${DKMS_NAME}/${DKMS_VER}" 2>/dev/null | grep -q "${DKMS_NAME}"; then
    warn "Removing previous DKMS installation..."
    dkms remove "${DKMS_NAME}/${DKMS_VER}" --all 2>/dev/null || true
    rm -rf "${DKMS_DST}"
fi

# Copy source to DKMS directory
info "Copying source to ${DKMS_DST}..."
mkdir -p "${DKMS_DST}"
rsync -a "${DKMS_SRC_DIR}/" "${DKMS_DST}/"

# DKMS add, build, install
info "Registering with DKMS..."
dkms add "${DKMS_NAME}/${DKMS_VER}"
info "Building with DKMS (this may take a few minutes)..."
dkms build "${DKMS_NAME}/${DKMS_VER}"
info "Installing with DKMS..."
dkms install "${DKMS_NAME}/${DKMS_VER}"

# Load
info "Loading driver..."
modprobe mt7603usta 2>/dev/null || true
sleep 3

if lsmod | grep -q mt7603usta; then
    info "Driver loaded successfully! It will auto-rebuild on kernel updates."
    ip link show | grep -A1 "wlx\|ra0" 2>/dev/null || warn "No interface detected. Try re-plugging the USB device."
    echo ""
    info "Connect WiFi: nmcli device wifi connect \"SSID\" password \"PASSWORD\""
else
    warn "Module installed but loading may require re-plugging the USB device."
fi
info "To uninstall, run: sudo bash dkms-uninstall.sh"
