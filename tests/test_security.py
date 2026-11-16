import asyncio
import io
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
import tg_common
import tg_runner
import swpulse


class StorageTests(unittest.TestCase):
    def test_atomic_json_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            tg_common.write_json(path, {'share': False})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_only_rfc1918_physical_active_interfaces(self):
        def interface(name, address, active=True):
            return f'{name}: flags=8863\n inet {address} netmask 0xffffff00\n status: {"active" if active else "inactive"}\n'
        raw = interface('en0', '192.168.40.2') + interface('utun1', '10.0.0.2') + interface('en1', '203.0.113.2') + interface('en2', '10.0.0.3', False)
        self.assertEqual(tg_common.lan_interfaces(raw), {'192.168.40.2': '192.168.40.0/24'})

    def test_log_redacts_secret_and_exception(self):
        secret = 'test-private-key-value'
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(tg_runner.RedactingFormatter(secret))
        logger = logging.Logger('test'); logger.addHandler(handler)
        try:
            raise ValueError(secret.upper())
        except ValueError:
            logger.exception('connection tg://proxy?secret=%s', secret)
        self.assertNotIn(secret.lower(), stream.getvalue().lower())
        self.assertNotIn('tg://', stream.getvalue())
        self.assertIn('REDACTED', stream.getvalue())

    def test_failed_dns_enable_restores_backup_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = {'Wi-Fi': [], 'Ethernet': ['192.168.1.1']}
            def setdns(service, addresses):
                if service == 'Ethernet' and addresses == ['127.0.0.1']:
                    raise RuntimeError('simulated write failure')
                current[service] = addresses
            with patch.object(swpulse, 'STATE', Path(tmp) / 'backup.json'), patch.object(swpulse, 'physical_services', return_value=list(current)), patch.object(swpulse, 'get', side_effect=lambda s: current[s]), patch.object(swpulse, 'setdns', side_effect=setdns), patch.object(swpulse, 'run', return_value='status: NOERROR ANSWER: 1'):
                with self.assertRaisesRegex(RuntimeError, 'simulated'):
                    swpulse.main('on')
                self.assertEqual(current, {'Wi-Fi': [], 'Ethernet': ['192.168.1.1']})
                self.assertEqual(swpulse.STATE.read_text(), '{}')


class FakeWriter:
    closed = False
    def get_extra_info(self, key):
        return ('192.168.40.3', 1234)
    def close(self):
        self.closed = True


class ForwardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_accept_after_share_off_is_rejected(self):
        forwarder = tg_runner.LANForwarder(1443)
        writer = FakeWriter()
        with patch('asyncio.open_connection') as connect:
            await forwarder.relay(None, writer, '192.168.40.2', '192.168.40.0/24')
            connect.assert_not_called()
        self.assertTrue(writer.closed)

    async def test_old_network_callback_is_rejected(self):
        forwarder = tg_runner.LANForwarder(1443)
        forwarder.bindings = {'192.168.40.2': '192.168.40.0/28'}
        writer = FakeWriter()
        with patch('asyncio.open_connection') as connect:
            await forwarder.relay(None, writer, '192.168.40.2', '192.168.40.0/24')
            connect.assert_not_called()
        self.assertTrue(writer.closed)

    async def test_stop_cancels_existing_connections(self):
        forwarder = tg_runner.LANForwarder(1443)
        task = asyncio.create_task(asyncio.sleep(60))
        forwarder.connections.add(task)
        await forwarder.close_connections()
        self.assertTrue(task.cancelled())

if __name__ == '__main__':
    unittest.main()
