"""Hotspot-only routing and forwarding; leave Mihomo's own policy intact."""
import ipaddress
import json

from common import cmd

PRIVATE_NETWORKS = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')


def check_proxy(config):
    if config['bypass_mihomo']:
        return
    tun = config['mihomo_tun']
    links = json.loads(cmd(['ip', '-j', 'link', 'show', 'dev', tun]))
    if not links or 'UP' not in links[0].get('flags', []):
        raise RuntimeError(f'Mihomo TUN 接口 {tun} 未启用；请先启动 Mihomo。')
    table = str(config['mihomo_table'])
    rules = json.loads(cmd(['ip', '-j', '-4', 'rule']))
    if not any(str(r.get('table')) == table for r in rules):
        raise RuntimeError(f'没有 Mihomo 路由表 {table} 的策略规则，请检查 auto-route。')
    routes = json.loads(cmd(['ip', '-j', '-4', 'route', 'show', 'table', table]))
    networks = [ipaddress.ip_network(r.get('dst', 'default').replace('default', '0.0.0.0/0'))
                for r in routes if r.get('dev') == tun and r.get('type', 'unicast') == 'unicast']
    if not networks or any(not any(ipaddress.ip_address(dns) in net for net in networks)
                           for dns in config['dns'].split(',')):
        raise RuntimeError('Mihomo TUN 路由未覆盖配置的 DNS 地址，请检查 auto-route 和排除网段。')


def network_changes(config, iface):
    """Yield reversible commands in insertion order (iptables -I prepends)."""
    uplink, subnet = config['uplink'], config['subnet']
    if config['bypass_mihomo']:
        spec = ['priority', '8000', 'iif', iface, 'lookup', 'main']
        yield ['ip', 'rule', 'add'] + spec, ['ip', 'rule', 'del'] + spec
    # Replies must return to clients rather than being captured by the TUN.
    spec = ['priority', '8001', 'to', subnet, 'lookup', 'main']
    yield ['ip', 'rule', 'add'] + spec, ['ip', 'rule', 'del'] + spec

    forwards = []
    if config['bypass_mihomo']:
        forwards.append(['-i', iface, '-o', uplink, '-s', subnet, '-j', 'ACCEPT'])
    else:
        # Prevent public traffic falling back to the wired gateway if TUN stops.
        # The LAN exceptions below are inserted ahead of this rejection.
        forwards.append(['-i', iface, '-o', uplink, '-s', subnet, '-j', 'REJECT'])
        for private in PRIVATE_NETWORKS:
            forwards.append(['-i', iface, '-o', uplink, '-s', subnet, '-d', private, '-j', 'ACCEPT'])
        forwards.extend([
            ['-i', iface, '-o', config['mihomo_tun'], '-s', subnet, '-j', 'ACCEPT'],
            ['-i', config['mihomo_tun'], '-o', iface, '-d', subnet,
             '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'],
        ])
        # This hotspot supplies IPv4 DHCP only; do not leak forwarded IPv6.
        spec = ['-m', 'comment', '--comment', 'nas-wifi', '-i', iface, '-j', 'REJECT']
        yield ['ip6tables', '-w', '5', '-I', 'FORWARD', '1'] + spec, \
              ['ip6tables', '-w', '5', '-D', 'FORWARD'] + spec
    forwards.append(['-i', uplink, '-o', iface, '-d', subnet,
                     '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'])
    entries = [('filter', 'FORWARD', spec) for spec in forwards]
    entries.append(('nat', 'POSTROUTING', ['-s', subnet, '-o', uplink, '-j', 'MASQUERADE']))
    for table, chain, spec in entries:
        spec = ['-m', 'comment', '--comment', 'nas-wifi'] + spec
        yield ['iptables', '-w', '5', '-t', table, '-I', chain, '1'] + spec, \
              ['iptables', '-w', '5', '-t', table, '-D', chain] + spec
