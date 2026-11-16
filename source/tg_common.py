import ipaddress
import json
import os
import pathlib
import re
import secrets
import subprocess
import tempfile

BASE = pathlib.Path.home() / 'Library/Application Support/SWPulse'
CONFIG = BASE / 'tg-config.json'
SETTINGS = BASE / 'tg-settings.json'
RUNTIME = BASE / 'tg-runtime.json'
LABEL = 'ru.swpulse.telegram'
PLIST = pathlib.Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))

def private_storage():
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    BASE.chmod(0o700)

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    temp = pathlib.Path(temporary)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)

def load_config():
    private_storage()
    if not CONFIG.exists():
        original = pathlib.Path.home() / 'Library/Application Support/TgWsProxy/config.json'
        data = json.loads(original.read_text()) if original.exists() else {}
        data.setdefault('port', 1443)
        data.setdefault('secret', secrets.token_hex(16))
        data['host'] = '127.0.0.1'
        write_json(CONFIG, data)
    CONFIG.chmod(0o600)
    data = json.loads(CONFIG.read_text())
    if not re.fullmatch(r'[a-fA-F0-9]{32}', data.get('secret', '')):
        raise ValueError('Invalid TG WS Proxy secret')
    if not 1024 <= int(data['port']) <= 65535:
        raise ValueError('TG WS Proxy port must be between 1024 and 65535')
    return data

def settings():
    return json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {'share': False}

def lan_interfaces(text=None):
    if text is None:
        text = subprocess.run(['/sbin/ifconfig', '-a'], capture_output=True, text=True, timeout=5).stdout
    result = {}
    for block in re.split(r'(?m)(?=^\w[^\n]*: flags=)', text):
        if not re.match(r'^en\d+:', block) or 'status: active' not in block:
            continue
        for addr, mask in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-fA-F]+)', block):
            ip = ipaddress.ip_address(addr)
            # Bind only physical private LAN addresses, never VPN or public interfaces.
            if any(ip in network for network in PRIVATE_NETWORKS):
                netmask = str(ipaddress.IPv4Address(int(mask, 16)))
                result[addr] = str(ipaddress.ip_network(f'{addr}/{netmask}', strict=False))
    return result
