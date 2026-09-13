# MT7603U USB WiFi 驱动安装包

适用于 **Ubuntu 24.04 LTS**，内核 **6.17.0-14-generic**，架构 **x86_64**。

[English](README.md)

## 文件说明

```
├── mt7603usta.ko          # 预编译驱动模块
├── firmware/
│   ├── MT7603USTA.dat     # 驱动配置文件
│   └── mt7603_e2.bin      # 芯片固件
├── install.sh             # 预编译版 一键安装
├── uninstall.sh           # 预编译版 一键卸载
├── dkms-install.sh        # DKMS版 一键安装
├── dkms-uninstall.sh      # DKMS版 一键卸载
├── dkms/                  # DKMS 源码目录
│   ├── dkms.conf
│   └── (完整驱动源码)
├── README.md              # English documentation
└── README_zh.md           # 本文件
```

## 支持设备

| USB ID | 设备 |
|--------|------|
| `0e8d:760c` | 360随身WiFi 3 |
| `0e8d:7603` | 通用 MT7603U 设备 |

---

## 方式一：预编译安装（推荐，秒装）

适用于内核恰好为 **6.17.0-14-generic** 的系统，无需编译。

```bash
sudo bash install.sh
```

卸载：
```bash
sudo bash uninstall.sh
```

> ⚠️ 内核版本不匹配时无法使用，请改用方式二。

---

## 方式二：DKMS 安装（内核更新自动重编译）

使用 DKMS 从源码编译安装，内核更新后自动重新编译驱动。

```bash
sudo bash dkms-install.sh
```

卸载：
```bash
sudo bash dkms-uninstall.sh
```

---

## 连接 WiFi

```bash
# 扫描
nmcli device wifi list

# 连接
nmcli device wifi connect "SSID" password "密码"
```

## 注意事项

- 预编译版仅适用于内核 6.17.0-14-generic，其他版本请用 DKMS 安装
- 加载后如无网络接口，尝试重新插拔 USB 设备
- 两种安装方式只需选择其一，不要同时安装
