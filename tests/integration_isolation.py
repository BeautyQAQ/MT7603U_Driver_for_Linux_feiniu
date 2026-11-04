"""Run only in fresh user/network/mount namespaces; no real WiFi device is used.

python3 tests/integration_isolation.py
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import common
import isolation
import network


def prepare_sandbox():
    # Refuse to run against the host, including when invoked with sudo.
    parent = json.loads(os.environ['NAS_WIFI_TEST_PARENT_NAMESPACES'])
    for kind in ('user', 'net', 'mnt'):
        if os.stat(f'/proc/self/ns/{kind}').st_ino == parent[kind]:
            raise RuntimeError('Fresh user, network and mount namespaces are required.')
    if os.geteuid() != 0 or json.loads(common.cmd(['ip', '-j', 'link', 'show']))[0]['ifname'] != 'lo':
        raise RuntimeError('Expected an empty test network with mapped root privileges.')
    if len(json.loads(common.cmd(['ip', '-j', 'link', 'show']))) != 1:
        raise RuntimeError('Refusing to use a nonempty network namespace.')
    common.cmd(['mount', '--make-rprivate', '/'])
    common.cmd(['mount', '-t', 'tmpfs', 'tmpfs', '/run'])
    common.cmd(['mount', '-t', 'sysfs', 'sysfs', '/sys'])


class IsolationIntegration(unittest.TestCase):
    def setUp(self):
        self.failure = None
        self.return_failure = False
        self.undo = []
        self.ns = isolation.HotspotNamespace('ap-test', 'phy0', {'subnet': '192.168.77.0/24'})
        self.patcher = patch.object(isolation, 'cmd', side_effect=self.command)
        self.patcher.start()
        for name in ('phone', 'internet'):
            common.cmd(['ip', 'netns', 'add', name])
            common.cmd(['ip', 'netns', 'exec', name, 'ip', 'link', 'set', 'dev', 'lo', 'up'])
        common.cmd(['ip', 'link', 'set', 'dev', 'lo', 'up'])
        common.cmd(['sysctl', '-q', '-w', 'net.ipv4.ip_forward=1'])
        common.cmd(['ip', 'link', 'add', 'ap-test', 'type', 'veth', 'peer', 'name', 'phone0', 'netns', 'phone'])
        common.cmd(['ip', 'link', 'add', 'aux-test', 'type', 'veth', 'peer', 'name', 'aux-peer'])
        common.cmd(['ip', 'link', 'add', 'uplink0', 'type', 'veth', 'peer', 'name', 'router0', 'netns', 'internet'])
        common.cmd(['ip', 'address', 'add', '192.0.2.2/24', 'dev', 'uplink0'])
        common.cmd(['ip', 'link', 'set', 'dev', 'uplink0', 'up'])
        common.cmd(['ip', 'route', 'add', 'default', 'via', '192.0.2.1'])
        for args in (['address', 'add', '192.0.2.1/24', 'dev', 'router0'],
                     ['link', 'set', 'dev', 'router0', 'up'],
                     ['address', 'add', '203.0.113.1/32', 'dev', 'lo']):
            common.cmd(['ip', 'netns', 'exec', 'internet', 'ip'] + args)

    def command(self, args, **kwargs):
        args = [str(a) for a in args]
        prefix, rest = (args[:4], args[4:]) if args[:3] == ['ip', 'netns', 'exec'] else ([], args)
        if rest[0] == 'nmcli':
            return ''  # Never contact the host NetworkManager from the test.
        if Path(rest[0]).name == 'iw':
            # Simulate a wiphy with two interfaces using real veth devices.
            if rest[1:] == ['dev']:
                links = json.loads(common.cmd(prefix + ['ip', '-j', 'link', 'show']))
                names = [x['ifname'].split('@')[0] for x in links if x['ifname'].split('@')[0] in ('ap-test', 'aux-test')]
                return 'phy#0\n' + ''.join(' Interface ' + name + '\n' for name in names) if names else ''
            target = rest[-1]
            if self.return_failure and target != isolation.NAMESPACE:
                raise RuntimeError('injected move-back failure')
            for iface in ('ap-test', 'aux-test'):
                common.cmd(prefix + ['ip', 'link', 'set', 'dev', iface, 'netns', target])
            return ''
        if self.failure and self.failure in rest:
            self.failure = None
            raise RuntimeError('injected setup failure')
        return common.cmd(args, **kwargs)

    def tearDown(self):
        self.failure = None
        self.return_failure = False
        try:
            for backward in reversed(self.undo):
                common.cmd(backward)
            self.ns.close()
            for iface in ('ap-test', 'aux-test', 'uplink0'):
                common.cmd(['ip', 'link', 'del', iface], check=False)
            for name in ('phone', 'internet'):
                common.cmd(['ip', 'netns', 'del', name])
        finally:
            self.patcher.stop()

    def assert_restored(self):
        links = {x['ifname'].split('@')[0] for x in json.loads(common.cmd(['ip', '-j', 'link', 'show']))}
        self.assertTrue({'ap-test', 'aux-test'} <= links)
        self.assertNotIn(isolation.HOST_IFACE, links)
        self.assertFalse(isolation.NAMESPACE_PATH.exists())
        routes = json.loads(common.cmd(['ip', '-j', '-4', 'route', 'show', 'table', 'main']))
        self.assertFalse(any(x['dst'] in ('192.168.77.0/24', str(isolation.TRANSIT)) for x in routes))

    def test_routing_hides_interfaces_and_preserves_clients_and_nat(self):
        self.ns.start()
        self.assertFalse(Path('/sys/class/net/ap-test').exists())
        self.assertFalse(Path('/sys/class/net/aux-test').exists())
        common.cmd(self.ns.prefix + ['ip', 'address', 'add', '192.168.77.1/24', 'dev', 'ap-test'])
        common.cmd(self.ns.prefix + ['ip', 'link', 'set', 'dev', 'ap-test', 'up'])
        for args in (['address', 'add', '192.168.77.105/24', 'dev', 'phone0'],
                     ['link', 'set', 'dev', 'phone0', 'up'],
                     ['route', 'add', 'default', 'via', '192.168.77.1']):
            common.cmd(['ip', 'netns', 'exec', 'phone', 'ip'] + args)
        for direct in (True, False):
            config = dict(uplink='uplink0', subnet='192.168.77.0/24', bypass_mihomo=direct, mihomo_tun='Meta')
            for forward, backward in network.network_changes(config, isolation.HOST_IFACE):
                self.undo.append(backward)
                common.cmd(forward)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
                server.bind((isolation.HOST_IP, 0))
                server.settimeout(3)
                port = server.getsockname()[1]
                common.cmd(['ip', 'netns', 'exec', 'phone', sys.executable, '-c',
                            f'import socket; socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b"source-check",("{isolation.HOST_IP}",{port}))'])
                message, source = server.recvfrom(1024)
                self.assertEqual((message, source[0]), (b'source-check', '192.168.77.105'))
            # No return route exists in the simulated Internet namespace, so
            # replies prove the host MASQUERADE and client return path work.
            common.cmd(['ip', 'netns', 'exec', 'phone', 'ping', '-n', '-c', '1', '-W', '3', '203.0.113.1'])
            for backward in reversed(self.undo):
                common.cmd(backward)
            self.undo.clear()
        self.ns.close()
        self.assert_restored()

    def test_failure_before_and_after_wireless_move_rolls_back(self):
        for failing_step in ('net.ipv4.ip_forward=1', 'net.ipv6.conf.ap-test.disable_ipv6=1'):
            with self.subTest(failing_step=failing_step):
                self.failure = failing_step
                with self.assertRaisesRegex(RuntimeError, 'injected setup failure'):
                    self.ns.start()
                self.ns.close()
                self.assert_restored()

    def test_move_back_failure_keeps_namespace_for_recovery(self):
        self.ns.start()
        self.return_failure = True
        with self.assertRaisesRegex(RuntimeError, 'injected move-back failure'):
            self.ns.close()
        self.assertTrue(isolation.NAMESPACE_PATH.exists())
        self.assertFalse(Path('/sys/class/net/ap-test').exists())
        self.return_failure = False
        self.ns.close()
        self.assert_restored()


if __name__ == '__main__':
    if '--inside' not in sys.argv:
        env = os.environ.copy()
        env['NAS_WIFI_TEST_PARENT_NAMESPACES'] = json.dumps({
            kind: os.stat(f'/proc/self/ns/{kind}').st_ino for kind in ('user', 'net', 'mnt')})
        sys.exit(subprocess.run(['unshare', '--user', '--map-root-user', '--net', '--mount',
                                 '--propagation', 'private', sys.executable, __file__, '--inside'], env=env).returncode)
    sys.argv.remove('--inside')
    prepare_sandbox()
    unittest.main(verbosity=2)
