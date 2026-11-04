from contextlib import ExitStack
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import hotspot
import isolation
import test_validation as validation


class HiddenWorkerTests(unittest.TestCase):
    def run_worker(self, direct=False, fail_start=False):
        config = validation.ConfigTests().parse(validation.CONFIG.replace('[wifi]', '[wifi]\nhide_from_nas = true'))
        config['bypass_mihomo'] = direct
        commands, events, handlers, processes = [], [], {}, []
        ns = Mock(prefix=['ip', 'netns', 'exec', isolation.NAMESPACE], created=True)
        ns.close.side_effect = lambda: events.append('return-wireless')
        if fail_start:
            ns.start.side_effect = RuntimeError('namespace setup failed')

        def command(args, **kwargs):
            args = [str(x) for x in args]
            commands.append(args)
            if args[0] == 'nmcli' and 'GENERAL.NM-MANAGED' in args:
                return 'no' if any('managed' in x and 'no' in x for x in commands) else 'yes'
            if args[:3] == ['nmcli', 'device', 'set'] and args[-1] == 'yes':
                events.append('restore-networkmanager')
            if args[:3] == ['nft', '-j', 'list']:
                return json.dumps({'nftables': [{'table': {'name': 'mihomo', 'family': 'inet'}}]})
            if 'hostapd_cli' in Path(args[4] if args[:3] == ['ip', 'netns', 'exec'] else args[0]).name:
                if args[-1] == 'status':
                    handlers[signal.SIGTERM]()
                    return 'state=ENABLED'
            if '-j' in args:
                return '[]'
            return ''

        def popen(args, **kwargs):
            processes.append([str(x) for x in args])
            process = Mock()
            process.poll.return_value = None
            process.terminate.side_effect = lambda: events.append('stop-child')
            return process

        def path(value):
            if str(value) == '/sys/module/mt7603usta':
                return Mock(exists=lambda: True)
            if str(value) == '/proc/sys/net/ipv4/ip_forward':
                return Mock(read_text=lambda: '1')
            return Path(value)

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            for name in ('logs', 'state'):
                (root / name).mkdir()
            replacements = dict(load_config=Mock(return_value=config), check_driver=Mock(return_value=(Path('/module.ko'), 'kernel')),
                                check_namespace_driver=Mock(), check_proxy=Mock(), find_adapter=Mock(return_value='wifi-test'),
                                HotspotNamespace=Mock(return_value=ns), cmd=Mock(side_effect=command), Path=path,
                                RUN=root / 'run', LOG=root / 'logs', STATE=root / 'state')
            for name, replacement in replacements.items():
                stack.enter_context(patch.object(hotspot, name, replacement))
            stack.enter_context(patch.object(hotspot.os, 'chown'))
            stack.enter_context(patch.object(hotspot.time, 'sleep'))
            stack.enter_context(patch.object(hotspot.signal, 'signal', side_effect=lambda sig, handler: handlers.update({sig: handler})))
            stack.enter_context(patch.object(hotspot.subprocess, 'Popen', side_effect=popen))
            states = stack.enter_context(patch.object(hotspot, 'save_status'))
            result = hotspot.run()
            snapshots = [call.kwargs for call in states.call_args_list]
        return result, commands, processes, events, snapshots

    def test_hidden_worker_keeps_services_inside_and_forwarding_on_host(self):
        for direct in (False, True):
            with self.subTest(direct=direct):
                result, commands, processes, events, snapshots = self.run_worker(direct)
                self.assertEqual(result, 0)
                self.assertEqual(len(processes), 2)
                self.assertTrue(all(args[:4] == ['ip', 'netns', 'exec', isolation.NAMESPACE] for args in processes))
                address = next(args for args in commands if args[4:7] == ['ip', 'address', 'add'])
                self.assertEqual(address[:4], ['ip', 'netns', 'exec', isolation.NAMESPACE])
                filters = [args for args in commands if args[0] == 'iptables' and '-i' in args]
                self.assertTrue(filters)
                self.assertTrue(all('wifi-test' not in args for args in filters))
                self.assertTrue(any(isolation.HOST_IFACE in args for args in filters))
                if direct:
                    bypass = next(args for args in commands if args[:3] == ['nft', 'insert', 'rule'])
                    self.assertEqual(bypass[bypass.index('iifname') + 1], isolation.HOST_IFACE)
                running = next(data for data in snapshots if data['state'] == 'running')
                self.assertEqual(running['wireless_namespace'], isolation.NAMESPACE)
                self.assertEqual(events[-2:], ['return-wireless', 'restore-networkmanager'])
                self.assertEqual(events.count('stop-child'), 2)
                self.assertEqual(snapshots[-1]['cleanup_errors'], [])

    def test_namespace_start_failure_restores_management_without_starting_services(self):
        result, _, processes, events, snapshots = self.run_worker(fail_start=True)
        self.assertEqual(result, 1)
        self.assertEqual(processes, [])
        self.assertEqual(events, ['return-wireless', 'restore-networkmanager'])
        self.assertEqual(snapshots[-1]['state'], 'failed')
        self.assertEqual(snapshots[-1]['cleanup_errors'], [])


if __name__ == '__main__':
    unittest.main()
