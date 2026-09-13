# 驱动补丁记录

`local-driver.patch` 是相对上游基础提交 `1125639b7aef82bb821315a0ebd51f9ad104d7a5`
的两项本地修正记录：

- Linux 6.13+ 的监听信道回调参数兼容。
- `DARK_MODE=NO` 时重复构建的 USB ID 配置处理。

补丁已经合入 `driver/`。正常构建直接运行根目录 `./build.sh`，无需再次应用补丁；
构建程序也不会自动读取或应用该文件。

补丁路径相对于驱动根目录。在项目根目录可只读检查对应修改是否已存在：

```bash
git apply --reverse --check --directory=driver patches/local-driver.patch
```

该命令不会修改文件。只有在重建未修正的上游源码副本时才需要正向应用补丁。
修改驱动或同步上游后，需同步维护本记录，避免补丁与实际源码分离。
