import ipaddress
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import network
import test_validation as validation


class NetworkTests(unittest.TestCase):
    def config(self, direct=False):
        content = validation.CONFIG if direct else validation.CONFIG.replace('bypass_mihomo = true', 'bypass_mihomo = false').replace('dns = 192.168.4.1', 'dns = 1.1.1.1')
        return validation.ConfigTests().parse(content)

    def verdict(self, config, outgoing, destination, incoming='wifi0', established=False):
        """Evaluate the installed FORWARD chain for representative client packets."""
        commands = [f for f, _ in network.network_changes(config, 'wifi0')
                    if f[0] == 'iptables' and 'FORWARD' in f]
        for args in reversed(commands):
            def val(flag):
                return args[args.index(flag) + 1] if flag in args else None
            if val('-i') and val('-i') != incoming:
                continue
            if val('-o') and val('-o') != outgoing:
                continue
            if val('-d') and ipaddress.ip_address(destination) not in ipaddress.ip_network(val('-d')):
                continue
            if val('--ctstate') and not established:
                continue
            return val('-j')
        return 'DEFAULT'

    def test_proxy_public_traffic_cannot_fall_back_to_wired_gateway(self):
        self.assertEqual(self.verdict(self.config(), 'enp1s0', '1.1.1.1'), 'REJECT')

    def test_proxy_can_reach_lan_and_tun(self):
        c = self.config()
        self.assertEqual(self.verdict(c, 'enp1s0', '192.168.4.1'), 'ACCEPT')
        self.assertEqual(self.verdict(c, 'Meta', '8.8.8.8'), 'ACCEPT')
        self.assertEqual(self.verdict(c, 'wifi0', '192.168.77.104', 'Meta', True), 'ACCEPT')

    def test_unrelated_forwarding_is_untouched(self):
        self.assertEqual(self.verdict(self.config(), 'enp1s0', '1.1.1.1', 'docker0'), 'DEFAULT')

    def test_direct_mode_preserves_wired_internet_access(self):
        self.assertEqual(self.verdict(self.config(True), 'enp1s0', '1.1.1.1'), 'ACCEPT')

    def test_proxy_keeps_reply_route_without_incoming_bypass(self):
        routes = [f for f, _ in network.network_changes(self.config(), 'wifi0') if f[0] == 'ip']
        self.assertFalse(any('iif' in r for r in routes))
        self.assertTrue(any('to' in r and '192.168.77.0/24' in r for r in routes))

    def test_proxy_blocks_forwarded_ipv6_only_on_hotspot(self):
        rules = [f for f, _ in network.network_changes(self.config(), 'wifi0') if f[0] == 'ip6tables']
        self.assertEqual(len(rules), 1)
        self.assertIn('wifi0', rules[0])
        self.assertIn('REJECT', rules[0])

    def test_proxy_rejects_local_dns_without_dns_listener(self):
        with self.assertRaisesRegex(ValueError, '公网 DNS'):
            validation.ConfigTests().parse(validation.CONFIG.replace('bypass_mihomo = true', 'bypass_mihomo = false'))

    def test_proxy_missing_tun_fails_preflight(self):
        with patch.object(network, 'cmd', return_value='[]'):
            with self.assertRaisesRegex(RuntimeError, '未启用'):
                network.check_proxy(self.config())

    def test_proxy_dns_excluded_from_tun_fails_preflight(self):
        responses = [[{'flags': ['UP']}], [{'table': 2022}],
                     [{'dst': '8.0.0.0/8', 'dev': 'Meta'}]]
        with patch.object(network, 'cmd', side_effect=[json.dumps(x) for x in responses]):
            with self.assertRaisesRegex(RuntimeError, 'DNS'):
                network.check_proxy(self.config())

    def test_proxy_accepts_ready_tun(self):
        responses = [[{'flags': ['UP']}], [{'table': 2022}],
                     [{'dst': 'default', 'dev': 'Meta'}]]
        with patch.object(network, 'cmd', side_effect=[json.dumps(x) for x in responses]):
            network.check_proxy(self.config())


if __name__ == '__main__':
    unittest.main()
