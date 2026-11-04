import io
import ipaddress
import json
from pathlib import Path
import sys
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import network
import test_validation as validation


class NetworkTests(unittest.TestCase):
    def config(self, direct=False):
        content = validation.CONFIG if direct else validation.CONFIG.replace('bypass_mihomo = true', 'bypass_mihomo = false').replace('dns = 192.168.4.1', 'dns = 223.5.5.5,119.29.29.29')
        return validation.ConfigTests().parse(content)

    def verdict(self, config, outgoing, destination, incoming='wifi0', established=False,
                protocol='tcp', port=443, source='192.168.77.104'):
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
            if val('-s') and ipaddress.ip_address(source) not in ipaddress.ip_network(val('-s')):
                continue
            if val('-d') and ipaddress.ip_address(destination) not in ipaddress.ip_network(val('-d')):
                continue
            if val('-p') and val('-p') != protocol:
                continue
            if val('--dport') and int(val('--dport')) != port:
                continue
            if val('--ctstate') and not established:
                continue
            return val('-j')
        return 'DEFAULT'

    def test_gateway_allows_public_direct_routes_without_service_whitelists(self):
        c = self.config()
        for destination, protocol, port in [('1.1.1.1', 'udp', 53),
                                             ('101.133.230.39', 'udp', 22020),
                                             ('101.133.230.39', 'tcp', 443),
                                             ('8.210.96.6', 'udp', 11010)]:
            with self.subTest(destination=destination, protocol=protocol, port=port):
                self.assertEqual(self.verdict(c, 'enp1s0', destination,
                                              protocol=protocol, port=port), 'ACCEPT')

    def test_gateway_does_not_allow_spoofed_hotspot_source(self):
        self.assertEqual(self.verdict(self.config(), 'enp1s0', '1.1.1.1',
                                      source='172.17.0.2'), 'DEFAULT')

    def test_wired_return_rule_only_accepts_established_traffic(self):
        c = self.config()
        self.assertEqual(self.verdict(c, 'wifi0', '192.168.77.104', 'enp1s0', True), 'ACCEPT')
        self.assertEqual(self.verdict(c, 'wifi0', '192.168.77.104', 'enp1s0'), 'DEFAULT')

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

    def test_gateway_accepts_a_real_lan_dns_server(self):
        c = validation.ConfigTests().parse(validation.CONFIG.replace('bypass_mihomo = true', 'bypass_mihomo = false'))
        self.assertEqual(c['dns'], '192.168.4.1')

    def test_gateway_rejects_its_own_gateway_as_dns(self):
        with self.assertRaisesRegex(ValueError, '网关未提供 DNS'):
            validation.ConfigTests().parse(validation.CONFIG.replace('dns = 192.168.4.1', 'dns = 192.168.77.1'))

    def test_missing_proxy_does_not_prevent_gateway_startup(self):
        for response in ['[]', RuntimeError('TUN device does not exist')]:
            with self.subTest(response=str(response)):
                output = io.StringIO()
                kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
                with patch.object(network, 'cmd', **kwargs), redirect_stdout(output):
                    network.check_proxy(self.config())
                self.assertIn('热点仍可启动', output.getvalue())

    def test_missing_proxy_policy_warns_without_blocking_gateway(self):
        output = io.StringIO()
        with patch.object(network, 'cmd', side_effect=['[{"flags": ["UP"]}]', '[]']), redirect_stdout(output):
            network.check_proxy(self.config())
        self.assertIn('热点仍可启动', output.getvalue())

    def test_gateway_dns_may_be_outside_tun_routes(self):
        responses = [[{'flags': ['UP']}], [{'table': 2022}],
                     [{'dst': '8.0.0.0/8', 'dev': 'Meta'}]]
        output = io.StringIO()
        with patch.object(network, 'cmd', side_effect=[json.dumps(x) for x in responses]), redirect_stdout(output):
            network.check_proxy(self.config())
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
