import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import isolation


class IsolationTests(unittest.TestCase):
    def test_transit_rejects_overlapping_routes_and_hotspot_subnets(self):
        for subnet, routes in [('169.254.77.0/24', []),
                               ('192.168.77.0/24', [{'dst': '169.254.0.0/16'}])]:
            with self.subTest(subnet=subnet, routes=routes):
                with self.assertRaisesRegex(RuntimeError, '冲突'):
                    isolation.check_transit({'subnet': subnet}, routes)

    def test_default_route_and_running_owned_transit_are_allowed(self):
        routes = [{'dst': 'default'}, {'dst': '169.254.77.0/30', 'dev': isolation.HOST_IFACE}]
        isolation.check_transit({'subnet': '192.168.77.0/24'}, routes, running=True)
        with self.assertRaisesRegex(RuntimeError, '冲突'):
            isolation.check_transit({'subnet': '192.168.77.0/24'}, routes)

    def test_existing_namespace_is_never_adopted(self):
        with patch.object(Path, 'exists', return_value=True), patch.object(isolation, 'cmd') as command:
            with self.assertRaisesRegex(RuntimeError, '尚未清理'):
                isolation.check_available()
            command.assert_not_called()

    def test_existing_virtual_interface_is_never_adopted(self):
        with patch.object(Path, 'exists', return_value=False), \
                patch.object(isolation, 'cmd', return_value=json.dumps([{'ifname': isolation.HOST_IFACE}])):
            with self.assertRaisesRegex(RuntimeError, '拒绝覆盖'):
                isolation.check_available()

    def test_only_interfaces_of_the_target_wiphy_are_selected(self):
        info = 'phy#2\n Interface other0\nphy#0\n Interface auxiliary0\n Interface wifi0\n'
        self.assertEqual(list(isolation.wireless_interfaces(info, 'phy0')), ['auxiliary0', 'wifi0'])

    def test_close_does_not_touch_unowned_resources(self):
        ns = isolation.HotspotNamespace('wifi0', 'phy0', {})
        with patch.object(isolation, 'cmd') as command:
            ns.close()
            command.assert_not_called()

    def test_move_back_failure_preserves_namespace_and_virtual_link(self):
        ns = isolation.HotspotNamespace('wifi0', 'phy0', {})
        ns.created = ns.link_created = True

        def command(args):
            args = [str(a) for a in args]
            if args[-2:] == ['iw', 'dev'] or args[-2:] == [str(isolation.BASE / 'bin/iw'), 'dev']:
                return 'phy#0\n Interface wifi0\n'
            if 'netns' in args[4:]:
                raise RuntimeError('move failed')
            if 'del' in args:
                self.fail('Cleanup deleted resources before recovering the wireless device')
            return ''

        with patch.object(isolation, 'cmd', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'move failed'):
                ns.close()
        self.assertTrue(ns.created)

    def test_cleanup_preserves_namespace_containing_a_foreign_wiphy(self):
        ns = isolation.HotspotNamespace('wifi0', 'phy0', {})
        ns.created = True
        with patch.object(isolation, 'cmd', return_value='phy#9\n Interface other0\n') as command:
            with self.assertRaisesRegex(RuntimeError, '仍有无线设备'):
                ns.close()
        self.assertFalse(any('del' in call.args[0] for call in command.call_args_list))


if __name__ == '__main__':
    unittest.main()
