#!/usr/bin/python3
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from common import BASE, UNIT, LEGACY_UNIT, cmd, load_config, check_driver, find_adapter
from hotspot import run, save_status

STATE = BASE / 'state'

def active(unit):
    return cmd(['systemctl', 'is-active', unit], check=False) in ('active', 'activating', 'deactivating')

def read_status():
    p = STATE / 'hotspot-status.json'
    return json.loads(p.read_text()) if p.exists() else {'state': 'not_started'}

def preflight():
    config = load_config()
    module, vermagic = check_driver()
    for tool in ['ip', 'nmcli', 'nft', 'iptables', 'dnsmasq', 'modprobe', 'insmod', 'rmmod',
                 'systemd-run', 'systemctl', 'udevadm', 'busctl']:
        if not shutil.which(tool):
            raise RuntimeError(f'缺少命令：{tool}')
    for binary in ['iw', 'hostapd', 'hostapd_cli']:
        if 'not found' in cmd(['ldd', BASE / 'bin' / binary]):
            raise RuntimeError(f'{binary} 缺少动态库。')
    if not (Path('/sys/class/net') / config['uplink']).exists():
        raise RuntimeError('配置的有线出口不存在，请修改 config/hotspot.ini。')
    return config, module, vermagic

def ensure_driver(module):
    if Path('/sys/module/mt7603usta').exists():
        loaded = Path('/sys/module/mt7603usta/srcversion')
        expected = cmd(['modinfo', '-F', 'srcversion', module])
        if loaded.exists() and loaded.read_text().strip() != expected:
            print('复用当前已加载的驱动；新编译产物会在卸载后重新启动或重启 NAS 后使用。', flush=True)
        return
    statefile = STATE / 'driver-files.json'
    owned = json.loads(statefile.read_text()) if statefile.exists() else {}
    # Record only files this project creates. Existing firmware is reused only
    # if it is byte-for-byte equal; never overwrite an unrelated firmware file.
    for name in ('MT7603USTA.dat', 'mt7603_e2.bin'):
        src = BASE / 'firmware' / name
        dst = Path('/lib/firmware') / name
        content = src.read_bytes()
        if dst.exists():
            if dst.read_bytes() != content:
                raise RuntimeError(f'{dst} 已存在且内容不同，停止以免覆盖。')
        else:
            owned[name] = hashlib.sha256(content).hexdigest()
            statefile.write_text(json.dumps(owned, indent=2) + '\n')
            dst.write_bytes(content)
            dst.chmod(0o644)
    cmd(['modprobe', 'cfg80211'])
    os.sync()
    print('正在加载匹配当前内核的驱动……', flush=True)
    output = cmd(['insmod', module], timeout=45)
    (BASE / 'logs/driver-load.log').write_text(output + '\n')
    cmd(['udevadm', 'settle', '--timeout=10'], check=False)
    for _ in range(15):
        try:
            find_adapter()
            return
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError('驱动已加载但尚未找到网卡，请查看 sudo journalctl -k。')

def stop_unit(unit):
    if active(unit):
        cmd(['systemctl', 'stop', unit], timeout=120)

def start():
    config, module, _ = preflight()
    if active(UNIT):
        print('热点服务已经在运行。修改配置后请执行 sudo ./restart.sh。')
        return
    # The earlier test may still own the adapter/subnet. Stop its scoped unit
    # and require its cleanup to finish before taking over.
    if active(LEGACY_UNIT):
        print('正在停止之前的临时测试热点，再切换到本工程……', flush=True)
        stop_unit(LEGACY_UNIT)
    previous = read_status()
    if previous.get('cleanup_errors'):
        raise RuntimeError('上一次停止存在清理错误，请先检查 state/hotspot-status.json，避免重复添加规则。')
    ensure_driver(module)
    find_adapter()
    save_status(state='requested')
    print(cmd(['systemd-run', '--unit', UNIT, '--collect', '--property=TimeoutStopSec=90',
               '--property=Restart=no', '/usr/bin/python3', BASE / 'lib/manage.py', 'run']))
    print('等待热点就绪（最多 60 秒）……', flush=True)
    for _ in range(60):
        data = read_status()
        if data.get('state') == 'running':
            print(f'热点已启用：{config["ssid"]}\n持续运行至 sudo ./stop.sh；未配置开机启动。')
            return
        if data.get('state') in ('failed', 'stopped'):
            raise RuntimeError(f'热点未启动：{data.get("error")}。请查看 logs/ 和 ./status.sh。')
        if not active(UNIT):
            raise RuntimeError('后台进程已退出，请查看 logs/ 或 sudo journalctl -u nas-wifi.service。')
        time.sleep(1)
    raise RuntimeError('热点就绪尚未确认，请运行 ./status.sh 检查；可用 sudo ./stop.sh 停止。')

def stop():
    stop_unit(UNIT)
    # A single stop command also covers the preceding temporary-test session.
    stop_unit(LEGACY_UNIT)
    data = read_status()
    if data.get('cleanup_errors'):
        raise RuntimeError('热点已停止，但存在清理错误：' + json.dumps(data['cleanup_errors'], ensure_ascii=False))
    print('热点已关闭。本工程添加的运行时规则由后台进程撤销；驱动仍在内存中。')

def unload():
    stop()
    if Path('/sys/module/mt7603usta').exists():
        iface = find_adapter()
        managed = cmd(['nmcli', '-g', 'GENERAL.NM-MANAGED', 'device', 'show', iface])
        cmd(['nmcli', 'device', 'set', iface, 'managed', 'no'])
        time.sleep(5)
        cmd(['ip', 'link', 'set', 'dev', iface, 'down'])
        try:
            cmd(['rmmod', 'mt7603usta'], timeout=45)
        except Exception:
            cmd(['nmcli', 'device', 'set', iface, 'managed', managed], check=False)
            raise
    p = STATE / 'driver-files.json'
    if p.exists():
        owned = json.loads(p.read_text())
        for name, digest in owned.items():
            if name not in ('MT7603USTA.dat', 'mt7603_e2.bin'):
                raise RuntimeError('固件记录含未知文件，停止清理。')
            dst = Path('/lib/firmware') / name
            if dst.exists():
                if hashlib.sha256(dst.read_bytes()).hexdigest() != digest:
                    raise RuntimeError(f'{dst} 已被修改，保留该文件。')
                dst.unlink()
        p.unlink()
    print('驱动已卸载；之前已存在的固件文件保持原样。')

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if action == 'status':
        print('当前内核：' + os.uname().release)
        print('热点服务：' + cmd(['systemctl', 'is-active', UNIT], check=False))
        if active(LEGACY_UNIT):
            print('旧临时测试热点仍在运行；sudo ./start.sh 会切换到本工程。')
        data = read_status()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if data.get('state') == 'running' and not active(UNIT):
            print('注意：上面是历史状态，当前服务已不在运行。')
        return
    if action == 'check':
        config, module, vermagic = preflight()
        print(f'配置有效；SSID：{config["ssid"]}\n当前内核：{os.uname().release}\n驱动：{module}\nvermagic：{vermagic}\n检查通过（只读，不加载驱动、不修改网络）。')
        if Path('/sys/module/mt7603usta').exists():
            print('已识别无线接口：' + find_adapter())
        return
    if os.geteuid() != 0:
        raise RuntimeError('启停或加载驱动需要 root，请在 NAS 终端用 sudo 执行对应脚本。')
    if action == 'run':
        try:
            result = run()
        except Exception as exc:
            save_status(state='failed', error=str(exc), cleanup_errors=[])
            raise
        sys.exit(result)
    with (STATE / 'operation.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一个启停操作尚未完成。')
        if action == 'start':
            start()
        elif action == 'stop':
            stop()
        elif action == 'restart':
            preflight()  # Validate edited configuration before interrupting a working AP.
            stop()
            start()
        elif action == 'unload':
            unload()
        else:
            raise RuntimeError('未知操作。')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        sys.exit(str(exc))
