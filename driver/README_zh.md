# MT7603U USB WiFi 驱动

基于 Ralink 厂商驱动的 MT7603U USB 无线网卡 Linux 驱动，已适配 **Ubuntu 24.04 LTS (kernel 6.8 ~ 6.17+)**。

> 驱动版本: `JEDI.L0.MP1.mt7603u.v1.14` (来自 `include/os/rt_linux.h`)

---

## 支持设备

| USB ID | 芯片 | 已测试设备 |
|--------|------|-----------|
| `0e8d:760c` | MT7603U | 360随身WiFi 3 |
| `0e8d:7603` | MT7603U | 通用 MT7603U 设备 |

其他可能兼容的设备（未测试）:
- ogemray GWF-1D07 / GWF-1M02
- comfast CF-WU825N V2
- lb-link BL-WN620A(7603) / BL-M7603NU1
- mercury MW300UM V4

更多 USB ID 可在 `common/rtusb_dev_id.c` 中添加。

---

## 一键安装（推荐）

### 方式一：直接安装

> 当前构建的内核版本: `6.17.0-14-generic` (运行 `uname -r` 查看你的内核版本)

```bash
git clone https://github.com/Looong01/MT7603U_Driver_for_Linux.git
cd MT7603U_Driver_for_Linux
sudo bash install.sh
```

### 方式二：DKMS 安装（内核更新后自动重编译）

```bash
git clone https://github.com/Looong01/MT7603U_Driver_for_Linux.git
cd MT7603U_Driver_for_Linux
sudo bash dkms-install.sh
```

### 卸载

```bash
sudo bash uninstall.sh
```

---

## 手动编译安装

### 1. 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 24.04 LTS (Noble Numbat) |
| 内核版本 | 6.8+ (已测试 6.17.0-14-generic) |
| 编译工具 | gcc, make, build-essential |
| 内核头文件 | linux-headers-$(uname -r) |

安装依赖:

```bash
sudo apt update
sudo apt install build-essential linux-headers-$(uname -r)
```

### 2. 编译

```bash
make clean
make KSRC=/lib/modules/$(uname -r)/build DARK_MODE=NO -j$(nproc)
```

> **注意**: `DARK_MODE=NO` 参数是必需的，否则驱动会使用 `0x0DDF` 而非 `0x760C` 作为 USB ID，导致无法识别 360随身WiFi 等设备。

编译成功后，驱动文件位于 `os/linux/mt7603usta.ko`。

### 3. 安装固件

```bash
sudo cp mt7603_firmware/MT7603USTA.dat /lib/firmware/
sudo cp mt7603_firmware/mt7603_e2.bin /lib/firmware/
```

### 4. 安装并加载驱动

```bash
# 复制驱动到系统目录
sudo cp os/linux/mt7603usta.ko /lib/modules/$(uname -r)/kernel/drivers/net/wireless/
sudo depmod -a

# 加载驱动
sudo modprobe mt7603usta
```

或不安装到系统目录，临时加载（重启后失效）:

```bash
sudo insmod os/linux/mt7603usta.ko
```

### 5. 验证

```bash
# 检查驱动是否加载
lsmod | grep mt7603usta

# 查看网络接口 (应出现 wlx* 开头的接口)
ip link show

# 扫描 WiFi
nmcli device wifi list

# 连接 WiFi
nmcli device wifi connect "SSID" password "密码"
```

---

## 内核适配说明 (6.8+ 内核改动)

本驱动基于旧版 Ralink 厂商驱动，移植到新内核需要以下适配:

| 文件 | 修改内容 |
|------|---------|
| `os/linux/Makefile.6` | 添加 `ccflags-y += $(EXTRA_CFLAGS)` (新内核不再隐式传递 EXTRA_CFLAGS) |
| `include/os/rt_linux.h` | `asm/uaccess.h` → `linux/uaccess.h`, `asm/unaligned.h` → `linux/unaligned.h` |
| `os/linux/rt_linux.c` | `del_timer_sync()` → `timer_delete_sync()` |
| `os/linux/cfg80211/cfg80211.c` | 适配 cfg80211 回调签名变化: `tdls_mgmt` 增加 `link_id`、`change_beacon` 使用 `cfg80211_ap_update`、`set_monitor_channel` 增加 `net_device`、`set_wiphy_params` 增加 `radio_idx` |

---

## 故障排除

### 加载后无网络接口

```bash
# 检查 dmesg 日志
sudo dmesg | grep -iE "mt7603\|mt_drv\|error"

# 尝试重新插拔 USB 设备，然后:
sudo modprobe mt7603usta

# 或重启 NetworkManager
sudo systemctl restart NetworkManager
```

### 编译失败: 找不到内核头文件

```bash
sudo apt install linux-headers-$(uname -r)
```

### 卸载驱动

```bash
sudo rmmod mt7603usta      # 临时卸载 (不删除文件，重启后可用 modprobe 重新加载)
sudo bash uninstall.sh     # 完全卸载
```

### Kernel Panic

该驱动基于旧厂商代码，极端情况下可能导致内核崩溃。长按电源键强制重启即可恢复。如果使用了 `install.sh` 安装到系统目录，可在重启后执行 `sudo bash uninstall.sh` 卸载。

---

## Build for OpenWRT

use `Makefile.backports` as Makefile. After compile and load `mt7603usta.ko`, the netifd script will not work in OpenWRT. To start an AP, make a config file like `hostapd.conf`, then use the hostapd command manually.

---

## 原始信息

- 上游仓库: [GitLab](https://gitlab.com/ChalesYu/buildroot_platform_hardware_wifi_mtk_drivers_mt7603)
- mt7603u 分支: `pub-test-v20220304`
- mt7601u 分支: `mt7601u` (驱动版本 `JEDI.MP1.mt7601u.v1.11`)
- 固件来源: [OpenWRT mt76](https://github.com/openwrt/mt76/tree/master/firmware)
- 本驱动在主线 mt76 驱动支持 MT7603U USB 后将不再需要


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
 
