#!/bin/bash
# MT7603U USB WiFi Driver - DKMS Uninstall
set -e

DKMS_NAME="mt7603usta"
DKMS_VER="1.14"
DKMS_SRC="/usr/src/${DKMS_NAME}-${DKMS_VER}"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[ "$EUID" -ne 0 ] && error "Please run with sudo: sudo bash dkms-uninstall.sh"

# Unload
if lsmod | grep -q mt7603usta; then
    info "Unloading driver module..."
    rmmod mt7603usta
fi

# Remove DKMS
if command -v dkms &>/dev/null && dkms status "${DKMS_NAME}/${DKMS_VER}" 2>/dev/null | grep -q "${DKMS_NAME}"; then
    info "Removing DKMS..."
    dkms remove "${DKMS_NAME}/${DKMS_VER}" --all
fi

# Remove source
if [ -d "${DKMS_SRC}" ]; then
    info "Removing source directory..."
    rm -rf "${DKMS_SRC}"
fi

# Optionally remove firmware
read -rp "Also remove firmware files? [y/N] " ans
if [[ "$ans" == [yY] ]]; then
    rm -f /lib/firmware/MT7603USTA.dat
    rm -f /lib/firmware/mt7603_e2.bin
    info "Firmware removed"
fi

info "Uninstall complete!"
