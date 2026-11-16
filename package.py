#!/usr/bin/env python3
"""Create a clean, explicitly allowlisted source kit. Never includes runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ['.gitignore', 'README.md', 'README.txt', 'SECURITY.md', 'build.py',
         'package.py', 'install-dns.sh', 'Build and Install.command',
         'source/Pulsebar.swift', 'source/Icon.swift', 'source/swpulse.py',
         'source/dns_guard.py', 'source/network_check.py', 'source/tg_common.py',
         'source/tg_control.py', 'source/tg_runner.py', 'source/health.py',
         'tests/test_security.py', 'tests/test_install.py', 'source/__init__.py', 'tests/__init__.py']
PATTERNS = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
            r'\bAKIA[A-Z0-9]{16}\b', r'tg://proxy\?[^\s\"\x27]*secret=[a-fA-F0-9]{32,}',
            r'/' + r'Users/(?!Shared(?:/|\b))[^/\s]+/']

def scan(paths, known_secrets=()):
    for name in paths:
        path = ROOT / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
            raise ValueError('Refusing a symlink in publication input: ' + name)
        text = path.read_text()
        if any(re.search(pattern, text) for pattern in PATTERNS):
            raise ValueError('Possible credential or personal path in ' + name)
        if any(secret and secret.lower() in text.lower() for secret in known_secrets):
            raise ValueError('Installed secret found in ' + name)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-local-secrets', action='store_true', help='Compare with locally installed TG keys without displaying them')
    args = parser.parse_args()
    secrets = []
    if args.check_local_secrets:
        for folder, file in [('SWPulse', 'tg-config.json'), ('TgWsProxy', 'config.json')]:
            config = Path.home() / 'Library/Application Support' / folder / file
            if config.exists():
                secrets.append(json.loads(config.read_text()).get('secret', ''))
    scan(FILES, secrets)
    destination = ROOT / '.build/publish'
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    archive = ROOT / '.build/Pulsebar-Source.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as kit:
        for name in FILES:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
            kit.write(target, 'pulsebar/' + name)
    print(f'PASS: {len(FILES)} source files; no matching credentials or personal paths')
    print('SHA256:', hashlib.sha256(archive.read_bytes()).hexdigest())
    print('Source kit:', archive)

if __name__ == '__main__':
    main()
