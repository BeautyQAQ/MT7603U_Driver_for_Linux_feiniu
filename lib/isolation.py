"""Keep the AP in its own network namespace and route clients via a veth."""
import ipaddress
import json
import os
from pathlib import Path

from common import BASE, cmd

NAMESPACE = 'nas-wifi-ap'
NAMESPACE_PATH = Path('/run/netns') / NAMESPACE
HOST_IFACE = 'nwifi-host'
PEER_IFACE = 'nwifi-ap'
TRANSIT = ipaddress.IPv4Network('169.254.77.0/30')
HOST_ADDRESS = '169.254.77.1/30'
PEER_ADDRESS = '169.254.77.2/30'
HOST_IP = '169.254.77.1'
PEER_IP = '169.254.77.2'


def wireless_interfaces(info, target_phy):
    phy = None
    for line in info.splitlines():
        line = line.strip()
        if line.startswith('phy#'):
            phy = 'phy' + line[4:]
        elif phy == target_phy and line.startswith('Interface '):
            yield line.split(' ', 1)[1]


def check_transit(config, routes, running=False):
    if ipaddress.ip_network(config['subnet']).overlaps(TRANSIT):
        raise RuntimeError(f'热点子网与隐藏模式的内部网段 {TRANSIT} 冲突。')
    for route in routes:
        if running and route.get('dev') == HOST_IFACE:
            continue
        dst = route.get('dst', 'default')
        if dst != 'default' and ipaddress.ip_network(dst, strict=False).overlaps(TRANSIT):
            raise RuntimeError(f'隐藏模式的内部网段 {TRANSIT} 与现有路由 {dst} 冲突。')


def check_available():
    if NAMESPACE_PATH.exists():
        raise RuntimeError(f'网络空间 {NAMESPACE} 尚未清理；请检查 ./status.sh 和 README 的隐藏模式恢复说明。')
    links = json.loads(cmd(['ip', '-j', 'link', 'show']))
    if any(link['ifname'] in (HOST_IFACE, PEER_IFACE) for link in links):
        raise RuntimeError(f'隐藏模式的虚拟接口 {HOST_IFACE}/{PEER_IFACE} 已存在，拒绝覆盖。')


class HotspotNamespace:
    def __init__(self, iface, phy, config):
        self.iface = iface
        self.phy = phy
        self.config = config
        self.prefix = ['ip', 'netns', 'exec', NAMESPACE]
        self.created = False
        self.link_created = False

    def start(self):
        check_available()
        check_transit(self.config, json.loads(cmd(['ip', '-j', '-4', 'route', 'show', 'table', 'main'])))
        # Set ownership before each command so even a partially failed setup
        # is cleaned up. Never adopt an existing namespace or interface.
        self.created = True
        cmd(['ip', 'netns', 'add', NAMESPACE])
        self.link_created = True
        cmd(['ip', 'link', 'add', HOST_IFACE, 'type', 'veth',
             'peer', 'name', PEER_IFACE, 'netns', NAMESPACE])
        cmd(['nmcli', 'device', 'set', HOST_IFACE, 'managed', 'no'])
        cmd(['sysctl', '-q', '-w', f'net.ipv6.conf.{HOST_IFACE}.disable_ipv6=1'])
        cmd(['ip', 'address', 'add', HOST_ADDRESS, 'dev', HOST_IFACE])
        cmd(['ip', 'link', 'set', 'dev', HOST_IFACE, 'up'])
        cmd(self.prefix + ['ip', 'link', 'set', 'dev', 'lo', 'up'])
        cmd(self.prefix + ['sysctl', '-q', '-w', 'net.ipv4.ip_forward=1',
                           'net.ipv6.conf.all.disable_ipv6=1',
                           'net.ipv6.conf.default.disable_ipv6=1'])
        cmd(self.prefix + ['ip', 'address', 'add', PEER_ADDRESS, 'dev', PEER_IFACE])
        cmd(self.prefix + ['ip', 'link', 'set', 'dev', PEER_IFACE, 'up'])
        cmd(self.prefix + ['ip', 'route', 'add', 'default', 'via', HOST_IP, 'dev', PEER_IFACE])
        # Preserve client source addresses for Mihomo and do NAT only in the
        # host, using the same forwarding rules as the visible AP mode.
        cmd(['ip', 'route', 'add', self.config['subnet'], 'via', PEER_IP, 'dev', HOST_IFACE])
        for iface in wireless_interfaces(cmd([BASE / 'bin/iw', 'dev']), self.phy):
            cmd(['ip', 'link', 'set', 'dev', iface, 'down'])
        cmd([BASE / 'bin/iw', 'phy', self.phy, 'set', 'netns', 'name', NAMESPACE])
        cmd(self.prefix + ['sysctl', '-q', '-w', f'net.ipv6.conf.{self.iface}.disable_ipv6=1'])

    def close(self):
        if not self.created:
            return
        # Move the entire wiphy back, including the vendor's auxiliary P2P
        # interface. Do not delete a namespace if any wireless device remains.
        info = cmd(self.prefix + [BASE / 'bin/iw', 'dev'])
        for iface in wireless_interfaces(info, self.phy):
            cmd(self.prefix + ['ip', 'link', 'set', 'dev', iface, 'down'])
        if any(line.strip() == 'phy#' + self.phy[3:] for line in info.splitlines()):
            cmd(self.prefix + [BASE / 'bin/iw', 'phy', self.phy, 'set', 'netns', str(os.getpid())])
        if cmd(self.prefix + [BASE / 'bin/iw', 'dev']).strip():
            raise RuntimeError(f'{NAMESPACE} 内仍有无线设备，保留网络空间以便恢复。')
        links = json.loads(cmd(['ip', '-j', 'link', 'show']))
        if self.link_created and any(link['ifname'] == HOST_IFACE for link in links):
            # Deleting the veth also removes its peer and the transit routes.
            cmd(['ip', 'link', 'del', 'dev', HOST_IFACE])
        cmd(['ip', 'netns', 'del', NAMESPACE])
        self.created = False
