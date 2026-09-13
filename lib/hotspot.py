#!/usr/bin/python3
"""Manually started hotspot worker; runtime network changes are reversed on stop."""
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from common import BASE, UNIT, cmd, load_config, find_adapter, check_driver
RUN = Path('/run/nas-wifi')
TAG = 'nas-wifi'
LOG = BASE / 'logs'
STATE = BASE / 'state'

def save_status(**data):
    data['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    tmp = STATE / 'hotspot-status.tmp'
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o644)
    tmp.replace(STATE / 'hotspot-status.json')

def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    path.chmod(0o600)

def run():
    config = load_config()
    check_driver()
    IFACE = find_adapter()
    UPLINK = config['uplink']
    if UPLINK == IFACE:
        raise RuntimeError('有线出口不能是热点网卡本身。')
    SUBNET = config['subnet']
    ADDRESS = config['address']
    undo = []
    children = []
    logfiles = []
    stopping = False
    failure = None
    created_run = False
    def stop_signal(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    def change(forward, backward):
        # Record before execution so partial startup can also be undone.
        undo.append(backward)
        cmd(forward)
    def remove_proxy_exception():
        result = json.loads(cmd(['nft', '-j', 'list', 'chain', 'inet', 'mihomo', 'prerouting']))
        for item in result.get('nftables', []):
            rule = item.get('rule', {})
            if rule.get('comment') == TAG:
                cmd(['nft', 'delete', 'rule', 'inet', 'mihomo', 'prerouting', 'handle', rule['handle']])
    try:
        save_status(state='starting')
        if not Path('/sys/module/mt7603usta').exists():
            raise RuntimeError('Load the temporary driver first.')
        if Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() != '1':
            raise RuntimeError('IPv4 forwarding is disabled; inspect before changing global settings.')
        for route in json.loads(cmd(['ip', '-j', '-4', 'route', 'show', 'table', 'main'])):
            dst = route.get('dst', 'default')
            if dst != 'default' and ipaddress.ip_network(dst, strict=False).overlaps(ipaddress.ip_network(SUBNET)):
                raise RuntimeError(f'Test subnet conflicts with existing route: {dst}')
        rules = json.loads(cmd(['ip', '-j', '-4', 'rule']))
        if any(r.get('priority') in (8000, 8001) for r in rules):
            raise RuntimeError('Test routing priorities are in use.')
        addresses = json.loads(cmd(['ip', '-j', '-4', 'address', 'show', 'dev', IFACE]))
        if any(item.get('addr_info') for item in addresses):
            raise RuntimeError('Wireless interface already has IPv4 configuration.')
        RUN.mkdir(mode=0o755)
        created_run = True
        # dnsmasq drops to nobody; its leases stay in this test-only directory.
        lease_dir = RUN / 'dhcp'
        lease_dir.mkdir(mode=0o755)
        os.chown(lease_dir, 65534, 65534)
        leases = lease_dir / 'leases'
        leases.touch(mode=0o644)
        os.chown(leases, 65534, 65534)
        password = config['password']
        private_file(RUN / 'hostapd.conf', f'''interface={IFACE}
driver=nl80211
ctrl_interface={RUN}/control
ssid={config['ssid']}
hw_mode=g
channel={config['channel']}
ieee80211n=1
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase={password}
max_num_sta=8
''')
        private_file(RUN / 'dnsmasq.conf', f'''port=0
interface={IFACE}
bind-dynamic
dhcp-range={config['dhcp_start']},{config['dhcp_end']},{config['mask']},1h
dhcp-option=3,{config['gateway']}
dhcp-option=6,{config['dns']}
dhcp-authoritative
dhcp-leasefile={leases}
log-dhcp
log-facility=-
user=nobody
''')
        cmd(['dnsmasq', '--test', f'--conf-file={RUN}/dnsmasq.conf'])
        old_managed = cmd(['nmcli', '-g', 'GENERAL.NM-MANAGED', 'device', 'show', IFACE])
        change(['nmcli', 'device', 'set', IFACE, 'managed', 'no'],
               ['nmcli', 'device', 'set', IFACE, 'managed', old_managed])
        # NetworkManager removes its supplicant interface asynchronously. Allow
        # that teardown to finish before hostapd changes the interface to AP.
        time.sleep(5)
        if cmd(['nmcli', '-g', 'GENERAL.NM-MANAGED', 'device', 'show', IFACE]) != 'no':
            raise RuntimeError('NetworkManager still manages the test interface.')
        (LOG / 'wireless-before-ap.log').write_text(
            cmd([BASE / 'bin/iw', 'dev']) + '\n' +
            cmd(['busctl', '--system', '--timeout=3s', 'call', 'fi.w1.wpa_supplicant1',
                 '/fi/w1/wpa_supplicant1', 'fi.w1.wpa_supplicant1', 'GetInterface', 's', IFACE], check=False))
        change(['ip', 'address', 'add', ADDRESS, 'dev', IFACE],
               ['ip', 'address', 'del', ADDRESS, 'dev', IFACE])
        # Only this test interface/subnet uses the ordinary wired routing table.
        change(['ip', 'rule', 'add', 'priority', '8000', 'iif', IFACE, 'lookup', 'main'],
               ['ip', 'rule', 'del', 'priority', '8000', 'iif', IFACE, 'lookup', 'main'])
        change(['ip', 'rule', 'add', 'priority', '8001', 'to', SUBNET, 'lookup', 'main'],
               ['ip', 'rule', 'del', 'priority', '8001', 'to', SUBNET, 'lookup', 'main'])
        nft_tables = json.loads(cmd(['nft', '-j', 'list', 'tables']))
        if config['bypass_mihomo'] and any(x.get('table', {}).get('name') == 'mihomo' and x['table']['family'] == 'inet'
               for x in nft_tables['nftables']):
            undo.append(remove_proxy_exception)
            cmd(['nft', 'insert', 'rule', 'inet', 'mihomo', 'prerouting',
                 'iifname', IFACE, 'counter', 'return', 'comment', f'"{TAG}"'])
        for table, chain, spec in [
            ('filter', 'FORWARD', ['-i', IFACE, '-o', UPLINK, '-s', SUBNET, '-j', 'ACCEPT']),
            ('filter', 'FORWARD', ['-i', UPLINK, '-o', IFACE, '-d', SUBNET,
                                   '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT']),
            ('nat', 'POSTROUTING', ['-s', SUBNET, '-o', UPLINK, '-j', 'MASQUERADE']),
        ]:
            spec = ['-m', 'comment', '--comment', TAG] + spec
            change(['iptables', '-w', '5', '-t', table, '-I', chain, '1'] + spec,
                   ['iptables', '-w', '5', '-t', table, '-D', chain] + spec)
        for name, args in [
            ('hostapd', [str(BASE / 'bin/hostapd'), str(RUN / 'hostapd.conf')]),
            ('dnsmasq', ['dnsmasq', '--keep-in-foreground', f'--conf-file={RUN}/dnsmasq.conf']),
        ]:
            logfile = open(LOG / f'{name}.log', 'w')
            logfiles.append(logfile)
            children.append(subprocess.Popen(args, stdout=logfile, stderr=subprocess.STDOUT))
        started = time.monotonic()
        while not stopping:
            if any(p.poll() is not None for p in children):
                raise RuntimeError('A hotspot process exited; inspect logs/hostapd.log and logs/dnsmasq.log.')
            status = cmd([BASE / 'bin/hostapd_cli', '-p', RUN / 'control', '-i', IFACE, 'status'], check=False)
            stations = cmd([BASE / 'bin/hostapd_cli', '-p', RUN / 'control', '-i', IFACE, 'all_sta'], check=False)
            save_status(state='running' if 'state=ENABLED' in status else 'initializing',
                        ap=status, stations=stations, leases=leases.read_text(),
                        interface=cmd([BASE / 'bin/iw', 'dev', IFACE, 'info'], check=False))
            if time.monotonic() - started > 30 and 'state=ENABLED' not in status:
                raise RuntimeError('AP did not enable within 30 seconds.')
            for _ in range(5):
                if stopping:
                    break
                time.sleep(1)
    except Exception as exc:
        failure = str(exc)
        import traceback
        (LOG / 'hotspot-error.log').write_text(traceback.format_exc())
        # Capture kernel and manager evidence before cleanup changes the mode.
        for name, args in [
            ('wireless-failure.log', [str(BASE / 'bin/iw'), 'dev']),
            ('kernel-ap-test.log', ['journalctl', '-k', '--since=-10min', '--no-pager', '-n', '700']),
            ('networkmanager-ap-test.log', ['journalctl', '-u', 'NetworkManager', '-u', 'wpa_supplicant',
                                           '--since=-10min', '--no-pager', '-n', '150']),
        ]:
            try:
                (LOG / name).write_text(cmd(args, check=False) + '\n')
            except Exception as diagnostic_error:
                print(f'{name}: {diagnostic_error}', flush=True)
        print(failure, flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
        for f in logfiles:
            f.close()
        cleanup_errors = []
        for action in reversed(undo):
            try:
                action() if callable(action) else cmd(action)
            except Exception as exc:
                cleanup_errors.append(str(exc))
        # Retain lease data for diagnosis; permit a later test to reuse a clean directory.
        if created_run and RUN.exists():
            import shutil
            shutil.rmtree(RUN)
        save_status(state='failed' if failure else 'stopped', error=failure,
                    cleanup_errors=cleanup_errors)
    return 1 if failure else 0
