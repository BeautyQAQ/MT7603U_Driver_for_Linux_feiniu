import configparser
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parents[1]
UNIT = 'nas-wifi.service'
LEGACY_UNIT = 'nas-wifi-test.service'
os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'

def cmd(args, check=True, timeout=15):
    p = subprocess.run([str(a) for a in args], text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args}: {p.stdout.strip()}')
    return p.stdout.strip()

def kernel_name(value=None):
    value = value or os.uname().release
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]*', value):
        raise ValueError('无效的内核版本。')
    return value

def load_config(path=None):
    path = Path(path) if path else BASE / 'config/hotspot.ini'
    c = configparser.ConfigParser(interpolation=None)
    with path.open() as f:
        c.read_file(f)
    ssid = c.get('wifi', 'ssid')
    password = c.get('wifi', 'password')
    if not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(x) < 32 or ord(x) == 127 for x in ssid):
        raise ValueError('SSID 必须为 1–32 字节，不可包含控制字符。')
    if not 8 <= len(password) <= 63 or any(not 32 <= ord(x) <= 126 for x in password):
        raise ValueError('WPA2 密码必须为 8–63 个可打印 ASCII 字符。')
    channel = c.getint('wifi', 'channel', fallback=6)
    if channel not in range(1, 12):
        raise ValueError('此工程仅配置 2.4 GHz 的信道 1–11。')
    uplink = c.get('network', 'uplink', fallback='enp1s0')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', uplink):
        raise ValueError('有线接口名称无效。')
    address = ipaddress.IPv4Interface(c.get('network', 'address'))
    net = address.network
    start = ipaddress.IPv4Address(c.get('network', 'dhcp_start'))
    end = ipaddress.IPv4Address(c.get('network', 'dhcp_end'))
    if address.ip in (net.network_address, net.broadcast_address):
        raise ValueError('热点网关不能是网络地址或广播地址。')
    if not (net.network_address < start <= end < net.broadcast_address):
        raise ValueError('DHCP 地址池必须在热点子网内且不含网络/广播地址。')
    if start <= address.ip <= end:
        raise ValueError('DHCP 地址池不能包含热点网关。')
    dns = [str(ipaddress.IPv4Address(x.strip())) for x in c.get('network', 'dns').split(',')]
    bypass = c.getboolean('network', 'bypass_mihomo', fallback=True)
    tun = c.get('network', 'mihomo_tun', fallback='Meta')
    table = c.getint('network', 'mihomo_table', fallback=2022)
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', tun) or tun == uplink:
        raise ValueError('Mihomo TUN 接口名称无效，或与有线出口相同。')
    if not 1 <= table <= 4294967295 or table in (253, 254, 255):
        raise ValueError('Mihomo 路由表编号无效。')
    if not bypass and any(not ipaddress.IPv4Address(x).is_global for x in dns):
        raise ValueError('Mihomo 模式请使用公网 DNS 地址（如 1.1.1.1），由 TUN 劫持解析；不要填写热点网关或局域网 DNS。')
    return dict(ssid=ssid, password=password, channel=channel, uplink=uplink,
                address=str(address), subnet=str(net), gateway=str(address.ip),
                mask=str(net.netmask), dhcp_start=str(start), dhcp_end=str(end), dns=','.join(dns),
                bypass_mihomo=bypass, mihomo_tun=tun, mihomo_table=table)

def artifact_path(kernel=None):
    return BASE / 'build' / kernel_name(kernel) / 'mt7603usta.ko'

def check_driver(kernel=None):
    kernel = kernel_name(kernel)
    module = artifact_path(kernel)
    if not module.is_file():
        raise RuntimeError(f'缺少当前内核 {kernel} 的驱动，请先运行 ./build.sh（不需要 sudo）。')
    vermagic = cmd(['modinfo', '-F', 'vermagic', module])
    if not vermagic.split() or vermagic.split()[0] != kernel:
        raise RuntimeError(f'驱动与内核 {kernel} 不匹配，拒绝加载。请运行 ./build.sh 重新编译。')
    manifest_path = module.parent / 'build.json'
    if not manifest_path.is_file():
        raise RuntimeError('驱动缺少构建记录，请重新编译。')
    import hashlib
    manifest = json.loads(manifest_path.read_text())
    if hashlib.sha256(module.read_bytes()).hexdigest() != manifest['sha256']:
        raise RuntimeError('驱动文件与构建记录不一致，请重新编译。')
    return module, vermagic

def find_adapter():
    # The vendor driver reports usbcore as the module owner in sysfs; match the
    # USB VID/PID of the wiphy device instead of relying on that module link.
    candidates = []
    info = cmd([BASE / 'bin/iw', 'dev'])
    current = None
    modes = {}
    for line in info.splitlines():
        line = line.strip()
        if line.startswith('Interface '):
            current = line.split(' ', 1)[1]
        elif current and line.startswith('type '):
            modes[current] = line[5:]
    for netdev in Path('/sys/class/net').iterdir():
        phy = netdev / 'phy80211'
        if not phy.exists() or modes.get(netdev.name) not in ('managed', 'AP'):
            continue
        dev = (phy / 'device').resolve()
        for ancestor in (dev, *dev.parents):
            try:
                match = ((ancestor / 'idVendor').read_text().strip().lower() == '0e8d' and
                         (ancestor / 'idProduct').read_text().strip().lower() == '760c')
            except OSError:
                continue
            if match:
                candidates.append(netdev.name)
                break
    if len(candidates) != 1:
        raise RuntimeError(f'无法唯一识别 0e8d:760c 的无线接口：{candidates}。请检查驱动与 USB 设备。')
    return candidates[0]
