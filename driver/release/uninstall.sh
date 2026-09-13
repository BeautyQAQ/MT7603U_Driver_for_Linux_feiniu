#!/bin/bash
# MT7603U USB WiFi Driver - Uninstall
set -e

KVER="$(uname -r)"
MOD_DIR="/lib/modules/${KVER}/kernel/drivers/net/wireless"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[ "$EUID" -ne 0 ] && error "Please run with sudo: sudo bash uninstall.sh"

# Unload
if lsmod | grep -q mt7603usta; then
    info "Unloading driver module..."
    rmmod mt7603usta
fi

# Remove module file
if [ -f "${MOD_DIR}/mt7603usta.ko" ]; then
    info "Removing kernel module..."
    rm -f "${MOD_DIR}/mt7603usta.ko"
    depmod -a "${KVER}"
fi

# Optionally remove firmware
read -rp "Also remove firmware files? [y/N] " ans
if [[ "$ans" == [yY] ]]; then
    rm -f /lib/firmware/MT7603USTA.dat
    rm -f /lib/firmware/mt7603_e2.bin
    info "Firmware removed"
fi

info "Uninstall complete!"
