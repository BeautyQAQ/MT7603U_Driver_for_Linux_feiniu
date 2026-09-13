#!/bin/bash
# MT7603U USB WiFi Driver - Install (prebuilt binary)
# Built for: Ubuntu 24.04 LTS, kernel 6.17.0-14-generic, x86_64
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KVER="$(uname -r)"
MOD_DIR="/lib/modules/${KVER}/kernel/drivers/net/wireless"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[ "$EUID" -ne 0 ] && error "Please run with sudo: sudo bash install.sh"

# Check kernel version
BUILT_KVER="6.17.0-14-generic"
if [ "$KVER" != "$BUILT_KVER" ]; then
    warn "Current kernel ${KVER} differs from build kernel ${BUILT_KVER}"
    warn "Driver may fail to load. Consider rebuilding from source."
    read -rp "Continue anyway? [y/N] " ans
    [[ "$ans" != [yY] ]] && exit 0
fi

# Install firmware
info "Installing firmware..."
cp -f "${SCRIPT_DIR}/firmware/MT7603USTA.dat" /lib/firmware/
cp -f "${SCRIPT_DIR}/firmware/mt7603_e2.bin" /lib/firmware/

# Install kernel module
info "Installing kernel module..."
mkdir -p "${MOD_DIR}"
cp -f "${SCRIPT_DIR}/mt7603usta.ko" "${MOD_DIR}/"
depmod -a "${KVER}"

# Load
info "Loading driver..."
modprobe cfg80211 2>/dev/null || true
modprobe mt7603usta 2>/dev/null || insmod "${SCRIPT_DIR}/mt7603usta.ko" 2>/dev/null || true
sleep 3

if lsmod | grep -q mt7603usta; then
    info "Driver loaded successfully!"
    ip link show | grep -A1 "wlx\|ra0" 2>/dev/null || warn "No interface detected. Try re-plugging the USB device."
    echo ""
    info "Connect WiFi: nmcli device wifi connect \"SSID\" password \"PASSWORD\""
else
    warn "Load failed. Try re-plugging USB then run: sudo modprobe mt7603usta"
fi
info "To uninstall, run: sudo bash uninstall.sh"
