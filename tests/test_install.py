import importlib.util
from pathlib import Path
import tempfile
import plistlib
import shutil
import unittest
from unittest.mock import patch
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build
import package

class InstallTests(unittest.TestCase):
    def test_activation_failure_restores_existing_files_and_preserves_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            support = home / 'Library/Application Support/SWPulse'
            support.mkdir(parents=True)
            (support / 'swpulse.py').write_text('previous code')
            (support / 'tg-config.json').write_text('private fixture')
            legacy = home / 'Applications/SWPulse.app'
            (legacy / 'Contents').mkdir(parents=True)
            (legacy / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'ru.swpulse.menubar'}))
            def fail(*args):
                shutil.rmtree(legacy)
                (home / 'Applications/Pulsebar.app').mkdir()
                (support / 'swpulse.py').write_text('broken update')
                (support / 'health.py').write_text('new file')
                raise RuntimeError('simulated install failure')
            with patch.object(build, 'SUPPORT', support), patch.object(Path, 'home', return_value=home), patch.object(build, 'activate', side_effect=fail), patch.object(build.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(RuntimeError, 'simulated'):
                    build.install(None, None, None, None, None)
            self.assertEqual((support / 'swpulse.py').read_text(), 'previous code')
            self.assertEqual((support / 'tg-config.json').read_text(), 'private fixture')
            self.assertFalse((support / 'health.py').exists())
            self.assertFalse(list(support.glob('.rollback-*')))
            self.assertTrue((legacy / 'Contents/Info.plist').exists())
            self.assertFalse((home / 'Applications/Pulsebar.app').exists())

    def test_publication_allowlist_excludes_generated_private_data(self):
        self.assertEqual(len(package.FILES), len(set(package.FILES)))
        for name in package.FILES:
            self.assertFalse(name.endswith(('.json', '.log', '.zip', '.pem')))
            self.assertNotIn('.build', name)
            self.assertNotIn('reports/', name)

    def test_scanner_rejects_known_secret_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = 'a-private-fixture-value'
            (root / 'source.py').write_text(secret)
            with patch.object(package, 'ROOT', root):
                with self.assertRaises(ValueError) as caught:
                    package.scan(['source.py'], [secret])
            self.assertNotIn(secret, str(caught.exception))

if __name__ == '__main__':
    unittest.main()
