"""Hotspot-only routing and forwarding; leave Mihomo's own policy intact."""
import json

from common import cmd

def check_proxy(config):
    """Report proxy readiness without making it a hotspot startup dependency."""
    if config['bypass_mihomo']:
        return
    try:
        tun = config['mihomo_tun']
        links = json.loads(cmd(['ip', '-j', 'link', 'show', 'dev', tun]))
        if not links or 'UP' not in links[0].get('flags', []):
            raise RuntimeError(f'Mihomo TUN 接口 {tun} 未启用。')
        table = str(config['mihomo_table'])
        rules = json.loads(cmd(['ip', '-j', '-4', 'rule']))
        if not any(str(r.get('table')) == table for r in rules):
            raise RuntimeError(f'没有 Mihomo 路由表 {table} 的策略规则。')
        routes = json.loads(cmd(['ip', '-j', '-4', 'route', 'show', 'table', table]))
        if not any(r.get('dev') == tun and r.get('type', 'unicast') == 'unicast'
                   for r in routes):
            raise RuntimeError('Mihomo 路由表没有可用的 TUN 路由。')
    except RuntimeError as exc:
        print(f'提示：{exc} 热点仍可启动，流量按当前系统路由转发。', flush=True)


def network_changes(config, iface):
    """Yield reversible commands in insertion order (iptables -I prepends)."""
    uplink, subnet = config['uplink'], config['subnet']
    if config['bypass_mihomo']:
        spec = ['priority', '8000', 'iif', iface, 'lookup', 'main']
        yield ['ip', 'rule', 'add'] + spec, ['ip', 'rule', 'del'] + spec
    # Replies must return to clients rather than being captured by the TUN.
    spec = ['priority', '8001', 'to', subnet, 'lookup', 'main']
    yield ['ip', 'rule', 'add'] + spec, ['ip', 'rule', 'del'] + spec

    # Ordinary gateway forwarding: Mihomo owns capture and traffic selection.
    # Destinations it excludes, and traffic after a clean proxy stop, use uplink.
    forwards = [['-i', iface, '-o', uplink, '-s', subnet, '-j', 'ACCEPT']]
    if not config['bypass_mihomo']:
        forwards.extend([
            ['-i', iface, '-o', config['mihomo_tun'], '-s', subnet, '-j', 'ACCEPT'],
            ['-i', config['mihomo_tun'], '-o', iface, '-d', subnet,
             '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'],
        ])
        # This hotspot supplies IPv4 DHCP only; keep forwarded IPv6 disabled.
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
