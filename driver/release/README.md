# MT7603U USB WiFi Driver

For **Ubuntu 24.04 LTS**, kernel **6.17.0-14-generic**, architecture **x86_64**.

[中文说明](README_zh.md)

## File Structure

```
├── mt7603usta.ko          # Prebuilt driver module
├── firmware/
│   ├── MT7603USTA.dat     # Driver configuration
│   └── mt7603_e2.bin      # Chip firmware
├── install.sh             # Prebuilt install script
├── uninstall.sh           # Prebuilt uninstall script
├── dkms-install.sh        # DKMS install script
├── dkms-uninstall.sh      # DKMS uninstall script
├── dkms/                  # DKMS source directory
│   ├── dkms.conf
│   └── (full driver source)
├── README.md              # This file
└── README_zh.md           # Chinese documentation
```

## Supported Devices

| USB ID | Device |
|--------|--------|
| `0e8d:760c` | 360 Portable WiFi 3 |
| `0e8d:7603` | Generic MT7603U devices |

---

## Option 1: Prebuilt Install (recommended, instant)

For systems running exactly kernel **6.17.0-14-generic**. No compilation needed.

```bash
sudo bash install.sh
```

Uninstall:
```bash
sudo bash uninstall.sh
```

> ⚠️ Will not work if kernel version does not match. Use Option 2 instead.

---

## Option 2: DKMS Install (auto-rebuild on kernel updates)

Builds the driver from source via DKMS. Automatically rebuilds when the kernel is updated.

```bash
sudo bash dkms-install.sh
```

Uninstall:
```bash
sudo bash dkms-uninstall.sh
```

---

## Connecting to WiFi

```bash
# Scan
nmcli device wifi list

# Connect
nmcli device wifi connect "SSID" password "PASSWORD"
```

## Notes

- Prebuilt binary only works with kernel 6.17.0-14-generic; use DKMS for other versions
- If no network interface appears after loading, try re-plugging the USB device
- Choose only one installation method; do not install both simultaneously
