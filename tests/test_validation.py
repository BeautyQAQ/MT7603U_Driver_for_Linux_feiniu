import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import common
import manage

CONFIG = '''[wifi]
ssid = NAS测试
password = secret%with#symbols
channel = 6
[network]
uplink = enp1s0
address = 192.168.77.1/24
dhcp_start = 192.168.77.100
dhcp_end = 192.168.77.120
dns = 192.168.4.1
bypass_mihomo = true
'''

class ConfigTests(unittest.TestCase):
    def parse(self, content):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'hotspot.ini'
            p.write_text(content)
            return common.load_config(p)

    def test_unicode_ssid_and_literal_password_symbols(self):
        c = self.parse(CONFIG)
        self.assertEqual(c['ssid'], 'NAS测试')
        self.assertEqual(c['password'], 'secret%with#symbols')

    def test_reject_multiline_ssid_injection(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('ssid = NAS测试', 'ssid = NAS\n driver=other'))

    def test_reject_password_too_short(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('secret%with#symbols', 'short'))

    def test_utf8_ssid_byte_limit(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('NAS测试', '网' * 11))

    def test_reject_gateway_in_dhcp_pool(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('192.168.77.100', '192.168.77.1'))

    def test_reject_pool_outside_subnet(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('192.168.77.120', '192.168.78.120'))

    def test_reject_unsupported_channel(self):
        with self.assertRaises(ValueError):
            self.parse(CONFIG.replace('channel = 6', 'channel = 36'))

class KernelGuards(unittest.TestCase):
    def test_old_kernel_module_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'mt7603usta.ko'
            p.write_bytes(b'test-module')
            with patch.object(common, 'artifact_path', return_value=p), \
                 patch.object(common, 'cmd', return_value='6.17.0 SMP'):
                with self.assertRaisesRegex(RuntimeError, '不匹配'):
                    common.check_driver('6.18.18.c1032-trim')

    def test_modified_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'mt7603usta.ko'
            p.write_bytes(b'changed')
            (p.parent / 'build.json').write_text(json.dumps({'sha256': 'not-the-same'}))
            with patch.object(common, 'artifact_path', return_value=p), \
                 patch.object(common, 'cmd', return_value='6.18.18.c1032-trim SMP'):
                with self.assertRaisesRegex(RuntimeError, '构建记录不一致'):
                    common.check_driver('6.18.18.c1032-trim')

    def test_failed_preflight_does_not_stop_working_hotspot(self):
        with patch.object(manage, 'preflight', side_effect=RuntimeError('kernel mismatch')), \
             patch.object(manage, 'stop_unit') as stop:
            with self.assertRaises(RuntimeError):
                manage.start()
            stop.assert_not_called()

    def test_stop_does_not_depend_on_current_configuration(self):
        with patch.object(manage, 'load_config', side_effect=ValueError('bad edited config')), \
             patch.object(manage, 'stop_unit') as stop, \
             patch.object(manage, 'read_status', return_value={'state': 'stopped'}):
            manage.stop()
            self.assertEqual(stop.call_count, 2)

if __name__ == '__main__':
    unittest.main()
