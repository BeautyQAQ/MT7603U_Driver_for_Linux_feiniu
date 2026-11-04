# 历史验证记录

## 2026-11-02：普通网关分流与直连回退

- 移除热点 IPv4 公网转发拒绝和 EasyTier 地址/端口特例，允许热点子网经有线出口正常转发；保留 TUN 接入、NAT、回程状态规则和停止清理。
- Mihomo 未就绪时仅提示；实际在容器停止、Meta 接口消失的状态下成功重启热点。
- DHCP DNS 调整为 `223.5.5.5,119.29.29.29`；两者在无代理时均收到有效 UDP DNS 应答。原 `1.1.1.1` 在同一对照测试中未收到应答。
- 手机 Termux 的独立 `resolv.conf` 原为 Google DNS，已同步使用上述可直连解析器，原文件已备份。
- 24 项自动检查通过，当前内核驱动预检查和 Git diff 格式检查通过。
- 真我 RMX2205 手机连接 `FN-NAS`，Wi-Fi 地址 `192.168.77.102`，EasyTier 节点 `q3pro` / `192.168.20.11`。
- 代理正常：Google 连通性端点 HTTP 204，百度 HTTP 200；Mihomo API 实测手机的 Google 流量匹配 Google 规则并选择代理出站。
- 代理停止：确认容器运行状态为 false、热点为 active；手机默认 curl 访问百度和小米均 HTTP 200，Android 系统域名解析与 ping 正常。
- 代理恢复：Google HTTP 204、国内 HTTP 200；EasyTier 重新连接，能看到电脑、NAS、云服务器等节点；到 NAS 和云服务器虚拟地址各 3 次 ping 无丢包。
- NAS 修改前备份：`/home/ubuntu/nas-wifi-backups/20261102-204217-ordinary-gateway`（包含原热点配置，权限受限）。
- 手机 DNS 备份：`/data/data/com.termux/files/usr/etc/resolv.conf.before-gateway-20261102-210602`。
- 范围：IPv4 短时功能验证；未验证强杀后残留接管规则或长时间稳定性。Fake-IP 缓存切换注意事项见 README。

以下内容从原 README 归档，记录当时的验证结果，不代表当前运行状态。

## 2026-09-13：飞牛 NAS 热点与 Mihomo 接入

- 环境：飞牛内核 `6.18.18.c1032-trim`，MT7603U / USB `0e8d:760c`。
- 旧临时测试：手机完成 WPA2 认证，获取 `192.168.77.104`，用户确认上网可用。
- 工程迁移：从持久目录重新编译当前内核模块，当时直连热点服务正在运行。
- Mihomo 改造：21 项自动检查及当前内核/TUN 预检查通过；NAS 的 DNS 查询已验证由
  Mihomo 劫持并返回 Fake-IP。
- 当时待办：用户在 NAS 终端执行 `sudo ./restart.sh` 应用代理模式，再验证手机上网及
  Mihomo 实际出站；当时执行账号无免密 sudo。
- 未完成一天稳定性测试、NAS 重启测试，未设置开机启动。

后续记录应注明日期、内核、代码版本、执行命令和实际结果，区分自动测试、主机检查和手机验证。
