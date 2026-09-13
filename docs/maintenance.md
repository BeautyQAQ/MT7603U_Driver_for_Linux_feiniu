# 项目结构与维护

## 结构结论

本项目是一个 Git 仓库：在上游驱动外增加飞牛 NAS 热点管理工具。
现有分层适合当前规模，无需为目录整齐而移动驱动内部文件或引入子模块。
`driver/`、`lib/` 和资源目录由脚本通过工程根目录定位；修改路径时需要同时检查构建、
临时 systemd 服务启动命令和测试导入路径。运行期间不要移动工程。

```text
nas-wifi/
├── README.md                 # 安装、配置和日常操作入口
├── *.sh                      # build/check/start/status/stop/restart/unload
├── driver/                   # 上游驱动源码，包含本地兼容修正
├── lib/                      # Python 构建和热点管理实现
├── config/
│   ├── hotspot.ini.example   # 提交到 Git 的配置模板
│   └── hotspot.ini           # 本地配置，Git 忽略
├── bin/                      # 随项目提供的用户态可执行文件
├── firmware/                 # 热点工具实际读取的固件与驱动配置
├── patches/                  # 已合入驱动的补丁记录
├── docs/                     # 维护说明与历史验证
├── tests/                    # 无需 root 的自动测试
├── build/                    # 本地产物，Git 忽略
├── logs/                     # 运行日志，Git 忽略
└── state/                    # 运行状态与资源记录，Git 忽略
```

根目录的七个 shell 脚本都是很薄的入口，保留现有 `./start.sh` 等命令方便日常操作。
`lib/` 当前只有五个 Python 文件，现阶段没有必要增加 Python 打包层。
本机还有一个空的 `scripts/` 目录，未被 Git 跟踪、无代码引用，也不是克隆后的必要结构；
后续维护脚本确有需要时再使用它。

## 上游来源与差异

- 上游：[Looong01/MT7603U_Driver_for_Linux](https://github.com/Looong01/MT7603U_Driver_for_Linux)。
- 基础提交：`1125639b7aef82bb821315a0ebd51f9ad104d7a5`。
- 当前 fork：[BeautyQAQ/MT7603U_Driver_for_Linux_feiniu](https://github.com/BeautyQAQ/MT7603U_Driver_for_Linux_feiniu)。
- 上游原来位于仓库根目录的内容，在本工程统一放入 `driver/`。

2026-09-13 对本地 Git 对象的核对结果：相对于上述基础提交，`driver/` 没有新增或删除文件，
仅 `Makefile` 和 `os/linux/cfg80211/cfg80211.c` 两个文件发生内容变化。
这两项变化已记录在 [local-driver.patch](../patches/local-driver.patch)。
该比较未核实远端最新提交。

维护时以 `driver/` 为实际编译源码，同时更新补丁记录与基础提交说明。
构建流程不会自动应用 `patches/` 下的文件，具体约定见 [补丁说明](../patches/README.md)。
上游与本工程的路径前缀不同，同步时需要将上游变更映射到 `driver/` 并审查本地修正，
不能直接用上游根目录覆盖本工程根目录。

## 容易混淆的资源

| 位置 | 用途和维护约定 |
|---|---|
| `driver/release/` | 上游历史发布内容，带 DKMS 源码副本、安装脚本和预编译模块；本项目构建时已排除此目录 |
| `build/<内核版本>/` | 本项目实际使用的驱动产物，必须由根目录 `build.sh` 构建 |
| `firmware/` | `lib/manage.py` 加载驱动时使用的资源；修改后需重新核对设备行为 |
| `driver/mt7603_firmware/`、`driver/release/firmware/` | 上游保留的固件副本，热点管理工具不从这里读取 |
| `bin/` | 当前提供 x86-64 动态链接程序，不适用于所有 CPU 架构；不放内核构建产物或项目脚本 |

本次核对中，根目录的两个固件文件与上述两处上游副本均逐字节相同。
保留独立的 `firmware/` 使运行资源路径清楚，重复数据约 74 KiB，暂不需要去重。

`driver/release/` 有 798 个跟踪文件，文件内容合计约 114.5 MiB，包含在 `driver/`
约 143.2 MiB 的跟踪文件中。这是以后精简工作树最值得评估的部分。
当前保留它以便对照上游；若以后移出，应同步修订上游说明和安装入口。
删除工作树文件不会移除 Git 历史中的旧对象，因此不会直接消除克隆历史的体积。

`bin/` 目前缺少可核实的原始包版本、下载来源和获取步骤。后续更新这些程序时应一并记录
包名、版本、架构、来源、校验值及随包版权信息；不要根据现有二进制猜测原始包版本。

## 本地数据与验证

`config/hotspot.ini`、`build/`、`logs/`、`state/` 和 Python 缓存已由根目录 `.gitignore` 排除。
`state/` 包含清理网络和固件时需要的记录，不应在热点运行时当作普通缓存删除。
构建工作目录会保留用于诊断，长期使用时会增长；清理旧构建应避开正在编译的目录，
并保留仍需使用的模块及其 `build.json`。

构建记录中的 `source_commit` 是整个仓库的提交号，`source_diff_sha256` 是
`driver/` 下 Git 已跟踪文件相对 HEAD 的差异摘要，并不是补丁文件的校验值。

只改文档时检查链接和 `git diff --check` 即可。修改管理代码后运行：

```bash
python3 -m unittest discover -s tests -v
```

修改驱动或构建路径后，在具备匹配内核 headers 的主机执行 `./build.sh` 和 `./check.sh`。
自动测试通过不能替代驱动加载、手机 DHCP 和实际出站验证；实际验证结果归档到
[历史验证记录](validation.md)。
