# MT7603U USB WiFi Driver

Linux driver for MT7603U USB wireless adapters based on the Ralink vendor driver, adapted for **Ubuntu 24.04 LTS (kernel 6.8 ~ 6.17+)**.

> Driver version: `JEDI.L0.MP1.mt7603u.v1.14` (from `include/os/rt_linux.h`)

[中文文档](README_zh.md)

---

## Supported Devices

| USB ID | Chipset | Tested Device |
|--------|---------|---------------|
| `0e8d:760c` | MT7603U | 360 Portable WiFi 3 |
| `0e8d:7603` | MT7603U | Generic MT7603U devices |

Other potentially compatible devices (untested):
- ogemray GWF-1D07 / GWF-1M02
- comfast CF-WU825N V2
- lb-link BL-WN620A(7603) / BL-M7603NU1
- mercury MW300UM V4

Additional USB IDs can be added in `common/rtusb_dev_id.c`.

---

## Quick Install (Recommended)

### Option 1: Direct Install

> Current built kernel version: `6.17.0-14-generic` (run `uname -r` to check yours)

```bash
git clone https://github.com/Looong01/MT7603U_Driver_for_Linux.git
cd MT7603U_Driver_for_Linux
sudo bash install.sh
```

### Option 2: DKMS Install (auto-recompiles after kernel updates)

```bash
git clone https://github.com/Looong01/MT7603U_Driver_for_Linux.git
cd MT7603U_Driver_for_Linux
sudo bash dkms-install.sh
```

### Uninstall

```bash
sudo bash uninstall.sh
```

---

## Manual Build & Install

### 1. Prerequisites

| Item | Requirement |
|------|-------------|
| OS | Ubuntu 24.04 LTS (Noble Numbat) |
| Kernel | 6.8+ (tested on 6.17.0-14-generic) |
| Build tools | gcc, make, build-essential |
| Kernel headers | linux-headers-$(uname -r) |

Install dependencies:

```bash
sudo apt update
sudo apt install build-essential linux-headers-$(uname -r)
```

### 2. Build

```bash
make clean
make KSRC=/lib/modules/$(uname -r)/build DARK_MODE=NO -j$(nproc)
```

> **Note**: The `DARK_MODE=NO` flag is required. Otherwise the driver will use `0x0DDF` instead of `0x760C` as the USB ID, preventing devices like the 360 Portable WiFi from being recognized.

After a successful build, the driver module is located at `os/linux/mt7603usta.ko`.

### 3. Install Firmware

```bash
sudo cp mt7603_firmware/MT7603USTA.dat /lib/firmware/
sudo cp mt7603_firmware/mt7603_e2.bin /lib/firmware/
```

### 4. Install and Load the Driver

```bash
# Copy the driver to the system modules directory
sudo cp os/linux/mt7603usta.ko /lib/modules/$(uname -r)/kernel/drivers/net/wireless/
sudo depmod -a

# Load the driver
sudo modprobe mt7603usta
```

Or load temporarily without installing to the system directory (lost after reboot):

```bash
sudo insmod os/linux/mt7603usta.ko
```

### 5. Verify

```bash
# Check if the driver is loaded
lsmod | grep mt7603usta

# Check network interfaces (a wlx* interface should appear)
ip link show

# Scan for WiFi networks
nmcli device wifi list

# Connect to a WiFi network
nmcli device wifi connect "SSID" password "your_password"
```

---

## Kernel Adaptation Notes (6.8+ Kernel Changes)

This driver is based on the legacy Ralink vendor driver. The following changes were needed to port it to newer kernels:

| File | Changes |
|------|---------|
| `os/linux/Makefile.6` | Added `ccflags-y += $(EXTRA_CFLAGS)` (newer kernels no longer implicitly pass EXTRA_CFLAGS) |
| `include/os/rt_linux.h` | `asm/uaccess.h` → `linux/uaccess.h`, `asm/unaligned.h` → `linux/unaligned.h` |
| `os/linux/rt_linux.c` | `del_timer_sync()` → `timer_delete_sync()` |
| `os/linux/cfg80211/cfg80211.c` | Adapted cfg80211 callback signature changes: added `link_id` to `tdls_mgmt`, `change_beacon` now uses `cfg80211_ap_update`, added `net_device` to `set_monitor_channel`, added `radio_idx` to `set_wiphy_params` |

---

## Troubleshooting

### No Network Interface After Loading

```bash
# Check dmesg logs
sudo dmesg | grep -iE "mt7603\|mt_drv\|error"

# Try re-plugging the USB device, then:
sudo modprobe mt7603usta

# Or restart NetworkManager
sudo systemctl restart NetworkManager
```

### Build Fails: Kernel Headers Not Found

```bash
sudo apt install linux-headers-$(uname -r)
```

### Unload the Driver

```bash
sudo rmmod mt7603usta      # Temporary unload (files remain, can reload with modprobe after reboot)
sudo bash uninstall.sh     # Full uninstall
```

### Kernel Panic

This driver is based on legacy vendor code and may cause kernel panics in extreme cases. Hold the power button to force a reboot to recover. If you installed using `install.sh`, you can run `sudo bash uninstall.sh` after rebooting to uninstall.

---

## Build for OpenWRT

Use `Makefile.backports` as the Makefile. After compiling and loading `mt7603usta.ko`, the netifd script will not work in OpenWRT. To start an AP, create a config file like `hostapd.conf`, then use the hostapd command manually.

---

## Original Information

- Upstream repository: [GitLab](https://gitlab.com/ChalesYu/buildroot_platform_hardware_wifi_mtk_drivers_mt7603)
- mt7603u branch: `pub-test-v20220304`
- mt7601u branch: `mt7601u` (driver version `JEDI.MP1.mt7601u.v1.11`)
- Firmware source: [OpenWRT mt76](https://github.com/openwrt/mt76/tree/master/firmware)
- This driver will no longer be needed once the mainline mt76 driver supports MT7603U USB


### Test New USB Device ID

If a USB device is based on mt7603u and device id is `0E8D:0DDF` .

After insmod mt7603usta.ko , need to :

```
echo 0E8D 0DDF > /sys/bus/usb/drivers/mt_drv/new_id
```

to make driver actually load and work.


### Disable Dark Mode

This driver enabled Dark Mode as default.

A way to disabled it

```
sed -i '1s/#define/\/\/#define/g'  common/rtusb_dev_id.c
```

Or use a more easy way when compile

```
make KSRC=/lib/modules/$(uname -r)/build  DARK_MODE=NO
```
 
