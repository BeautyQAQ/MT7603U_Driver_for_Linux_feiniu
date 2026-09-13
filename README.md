# 飞牛 NAS / 360 随身 WiFi 热点

本仓库包含驱动源码和飞牛 NAS 热点管理工具。本机工程目录为 `/home/ubuntu/project/nas-wifi`，
克隆到其他目录也可以使用。

设备为 **MT7603U / USB 0e8d:760c**。已在飞牛 `6.18.18.c1032-trim` 上完成驱动加载、
WPA2 热点、手机获取 DHCP 地址和上网验证。源码、补丁、编译目录、产物和运行工具都保存在
本工程中，不依赖之前的 `/tmp` 目录。

这里提供手动管理脚本：不安装开机服务、不设置模块自动加载、不运行一天测试。
启动后没有 30 分钟期限，持续到手动停止或 NAS 重启。

## 日常使用

首次克隆后，先创建本地配置，修改热点名称、密码和网络参数，再编译当前内核的驱动：

```bash
git clone git@github.com:BeautyQAQ/MT7603U_Driver_for_Linux_feiniu.git
cd MT7603U_Driver_for_Linux_feiniu
install -m 600 config/hotspot.ini.example config/hotspot.ini
# 编辑 config/hotspot.ini，设置自己的密码和网络参数
./build.sh
./check.sh
```

真实配置、日志、运行状态和本地构建产物不提交到 Git。后续命令在自己的克隆目录内执行。

```bash
cd /home/ubuntu/project/nas-wifi

./check.sh           # 只读：检查配置、内核、驱动产物和工具
sudo ./start.sh      # 必要时加载驱动，然后启动热点
./status.sh         # 查看服务状态、热点状态、手机授权信息和 DHCP 租约
sudo ./stop.sh       # 关闭热点，撤销本工程添加的网络规则，驱动保留在内存
sudo ./restart.sh    # 检查配置后重启热点，让修改后的配置生效
sudo ./unload.sh     # 关闭热点并卸载驱动，不强制卸载使用中的模块
```

`start.sh` 成功时明确显示“热点已启用”，不会仅凭后台进程创建成功就报告热点可用。
如之前的 `nas-wifi-test.service` 仍在运行，`start.sh` 会先停止它，再由本工程接管，
切换期间手机会短暂断线；`stop.sh` 也能关闭旧测试服务。

脚本用 **临时 systemd 服务 `nas-wifi.service`** 管理后台进程，方便退出 SSH 后继续使用。
没有写入 `/etc/systemd/system`，没有执行 `systemctl enable`，NAS 重启后需手动运行 `start.sh`。
自动重启失败进程也未启用，避免不稳定驱动反复重试。

`stop.sh` 关闭的是热点；如希望驱动也不再运行，使用 `unload.sh`。
卸载时会让 NetworkManager 释放该网卡再关闭接口；不使用强制卸载。
如果驱动仍被占用或卸载失败，脚本会报告错误，不伪报成功。

## USB 网卡拔出与重新插入

正常操作顺序是：**停止热点并卸载驱动 → 拔出 USB → 重新插入 USB → 手动启动热点**。
插拔本身不会删除热点名称、密码和 Mihomo 配置。

### 拔出之前

在 NAS 终端执行：

```bash
cd /home/ubuntu/project/nas-wifi
sudo ./unload.sh
```

脚本会停止热点、清理本工程添加的网络规则并卸载驱动。看到“驱动已卸载”且命令成功结束后，
再拔出 USB 网卡。仅执行 `stop.sh` 会保留驱动，准备拔出时使用 `unload.sh`。
如果卸载报错，先保留网卡并检查错误，不要强制卸载。

### 重新插入之后

插回 USB 网卡，等待系统识别后执行：

```bash
cd /home/ubuntu/project/nas-wifi
sudo ./start.sh
./status.sh
```

脚本会按需加载驱动、识别网卡并使用原配置启动热点；看到“热点已启用”后即可让手机重新连接。
当前未配置插入后自动启动。使用 Mihomo 模式时，需先确保 Mihomo 正在运行且 TUN 已启用。
如果尚未识别到网卡，查看报错和 `./status.sh`，不要反复插拔。

如果期间更新了 NAS 内核，提示缺少驱动或版本不匹配时，先按“飞牛更新内核后”一节安装匹配的
headers，再执行 `./build.sh`、`./check.sh` 和 `sudo ./start.sh`。

### 如果已经直接拔掉

热点会立即消失，手机断网。NAS 的有线上网通常不受影响，但热点进程、路由及防火墙规则可能
未完成清理；本驱动的热拔插稳定性尚未验证，因此不建议把直接拔出作为日常操作。

如果 NAS 仍正常响应，先执行：

```bash
cd /home/ubuntu/project/nas-wifi
sudo ./stop.sh
./status.sh
```

确认没有清理错误后，再插回网卡并执行 `sudo ./start.sh`。如果出现清理错误或网卡无法重新识别，
保留终端输出和 `state/hotspot-status.json`，先排查，不要反复启动或强制卸载。
若 NAS 已失去响应，应先检查主机状态，不能保证能通过上述脚本恢复。

## 修改名称和密码

编辑 **`config/hotspot.ini`**。首次使用时按上面的命令从模板创建，权限为仅当前用户及 root 可读取；
本机已有配置可继续使用。

```ini
[wifi]
ssid = 我的NAS热点
password = YourNewPassword123
channel = 6
```

- SSID 长度为 1–32 个 UTF-8 字节；中文通常每字 3 字节。
- WPA2 密码为 8–63 个可打印 ASCII 字符，可以包含 `%`、`#` 等符号。
- 不要在值后面追加行内注释；不支持换行密码或换行 SSID。
- 当前配置是 2.4 GHz / WPA2-PSK / CCMP，信道限定为 1–11。
- 修改后先运行 `./check.sh`，再运行 `sudo ./restart.sh`。
- `config/hotspot.ini.example` 是不含真实密码的模板。

`[network]` 内还可以修改有线出口、热点网关/网段、DHCP 地址池和 DNS。
默认出口 `enp1s0`，热点网关 `192.168.77.1/24`，地址池 `.100`–`.120`。
启动前会检查与现有主路由表的子网冲突，避免覆盖原地址。

模板默认 `bypass_mihomo = false`，热点接入现有 Mihomo TUN，手机无需安装代理软件。
连接家庭路由器的设备仍使用原路由器上网；本工程不修改家庭路由器或 Mihomo 的全局规则。
Mihomo 按现有规则决定直连或代理，接入 TUN 并不等于所有网站都走国外节点。

```ini
[network]
# 保留其他网络参数
dns = 1.1.1.1
bypass_mihomo = false
mihomo_tun = Meta
mihomo_table = 2022
```

Mihomo 应运行于 NAS 主机网络（Docker 使用 host 网络），开启 `tun.enable`、`auto-route`、
`auto-redirect`，以及 `dns.enable`。`tun.dns-hijack` 需同时包含 `any:53` 和 `tcp://any:53`。
TUN 接口名、路由表号需要与上面的配置一致；启动前会检查接口、策略规则和到 DNS 的 TUN 路由。
这些检查不能替代对 Mihomo DNS 劫持和代理节点连通性的实际验证。
参见 [Mihomo TUN 文档](https://wiki.metacubex.one/config/inbound/tun/)。

`192.168.77.1` 是热点网关，本工程的 dnsmasq 仅提供 DHCP，没有在网关监听 DNS。
DHCP 下发的 `1.1.1.1` 是供 Mihomo 劫持的 DNS 目标，实际解析使用 Mihomo 的 DNS 配置。
代理模式不接受局域网 DNS 地址，避免被现有私网排除路由绕过。手机应使用自动 DNS；
手工配置的加密 DNS 不属于普通 53 端口劫持范围。

代理模式取消优先级 8000 的热点入站直连规则，保留 8001 的热点回程规则，并放行热点与 TUN
之间的转发。家庭私网仍可通过有线口访问；公网流量若退回有线口会被拒绝，避免 TUN 停止后
静默变成直连。当前热点提供 IPv4，代理模式阻止该热点接口转发 IPv6。

修改配置后执行 `./check.sh`、`sudo ./restart.sh`，再让手机断开并重新连接 WiFi 以更新 DHCP。
打开需要代理的网站，同时在 Mihomo 面板连接列表中检查手机的 `192.168.77.x` 来源、匹配规则
和实际出站节点。仅看到热点启动成功不能证明手机已通过代理上网。

若要恢复直连，设置 `bypass_mihomo = true`、`dns = 192.168.4.1` 后重启热点并重连手机。
直连模式会添加优先级 8000/8001 的路由，以及 Mihomo 对该热点接口的绕过规则。

本工程只添加带 `nas-wifi` 注释的 NAT/转发规则和上述独立策略路由。正常停止会逐项撤销，
不整体还原旧防火墙快照，也不清空 Docker 或其他服务的规则。
网卡按 USB ID 自动识别，不依赖 `wlx...` 名称或 `phy0`。

已验证此驱动需要等待 NetworkManager 的异步释放结束；脚本保留了 5 秒等待。
必须已经开启 IPv4 转发（这台 NAS 当前为 1）；若其他网络服务将其关闭，脚本会报告原因，
不会擅自修改全局转发设置。

## 飞牛更新内核后

每次 `start.sh` / `restart.sh` 都会核对运行内核、对应产物的 `vermagic` 和 SHA-256 构建记录。
没有当前内核的产物或版本不匹配时，会在加载驱动和中断现有热点之前停止。

```bash
cd /home/ubuntu/project/nas-wifi
uname -r
./check.sh
./build.sh           # 为当前运行的内核重新编译，不需要 sudo
./check.sh
sudo ./start.sh
```

编译需要 `/lib/modules/$(uname -r)/build` 指向**完全匹配该飞牛内核的 headers**。
若缺失，应先安装对应飞牛版本的内核头文件，不能拿通用 Debian 内核 headers 替代。
脚本不会自行升级内核、下载并安装不明驱动，也不会自动执行需要兼容性修正的补丁。
新内核 API 如果再次变化，编译可能失败；此时日志和源码会保留，现有产物不会被替换。

也可先为已安装 headers 的目标内核编译：`./build.sh 内核版本`。

产物按内核分开保存：

```text
build/<内核版本>/mt7603usta.ko  驱动模块
build/<内核版本>/build.json    内核版本、源码提交、补丁摘要和产物校验值
build/<内核版本>/build.log     编译日志
build/<内核版本>/work-*/       此次编译使用的独立工作目录
```

编译不会热替换内存中已加载的驱动。如果重新编译后要立即切换到新产物：

```bash
sudo ./unload.sh
sudo ./start.sh
```

`start.sh` 会复用当前已加载的同名驱动；发现它与磁盘产物源码版本不同会提示，
不会为了切换构建产物自行强制卸载正常使用中的驱动。

## 工程内容

| 路径 | 内容 |
|---|---|
| `driver/` | 保留上游内容并应用兼容性修正的驱动源码；与热点工具由根目录 Git 仓库统一管理 |
| `patches/local-driver.patch` | Linux 6.13+ 监听信道回调兼容修正、重复编译的 ID 配置修正 |
| `firmware/` | 已验证使用的驱动配置文件和固件 |
| `bin/` | Debian 12 amd64 的 iw、hostapd、hostapd_cli；使用系统动态库 |
| `lib/` | 配置检查、编译、驱动加载和热点管理代码 |
| `config/` | 用户配置和模板 |
| `logs/` | hostapd、dnsmasq 及失败诊断日志 |
| `state/` | 当前/最近运行状态和本工程创建的固件记录 |
| `tests/` | 无需 root、不会修改网络的检查测试 |

从任何工作目录执行这些 shell 脚本都可以；脚本自行定位工程。
请勿在运行期间移动工程目录。

`unload.sh` 只删除由本工程创建且内容未变的 `/lib/firmware` 文件；之前测试已经安装的
同名相同固件会复用而不覆盖，原有文件不会被本工程误删。工程文件本身会保留。

## 验证记录与限制

- 旧临时测试：2026-09-13 手机完成 WPA2 认证，获取 `192.168.77.104`，用户确认上网可用。
- 本工程：已从持久目录重新编译当前内核模块，直连热点服务正在运行。
- Mihomo 改造：21 项自动检查及当前内核/TUN 预检查通过；NAS 的 DNS 查询已验证由 Mihomo
  劫持并返回 Fake-IP。手机通过改造后的热点上网仍需重启热点后验证。
- 当前执行账号无免密 sudo，用户需在 NAS 终端执行 `sudo ./restart.sh` 应用代理模式，
  密码仅应输入 NAS 终端。
- 没有做一天稳定性测试，也没有进行 NAS 重启测试或设置开机启动。
- 第三方模块运行于内核中，崩溃可能影响整台 NAS；用户已确认可以接受测试风险并手动重启。
  手动启动模式下重启不会自动加载它，但不能保证正在写入的数据不受崩溃影响。

验证命令：`python3 -m unittest discover -s tests -v`。

上游：https://github.com/Looong01/MT7603U_Driver_for_Linux

上游基础提交：`1125639b7aef82bb821315a0ebd51f9ad104d7a5`。

本工程 fork：https://github.com/BeautyQAQ/MT7603U_Driver_for_Linux_feiniu 。

`driver/release/` 保留上游自带的发布文件，其中预编译模块不是本工程针对当前飞牛内核的构建产物；
热点管理脚本使用 `./build.sh` 生成的 `build/<内核版本>/mt7603usta.ko`。
