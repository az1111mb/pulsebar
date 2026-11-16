#!/opt/homebrew/bin/python3
"""Switch only physical macOS services; preserve DNS per enable cycle."""
import fcntl
import ipaddress
import json
import pathlib
import subprocess
import sys
from tg_common import private_storage, write_json

BASE = pathlib.Path.home() / 'Library' / 'Application Support' / 'SWPulse'
STATE = BASE / 'dns-backup.json'
DESIRED = BASE / 'desired-dns.json'
def physical_services():
    import re
    result = subprocess.run(['/usr/sbin/networksetup', '-listnetworkserviceorder'], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Could not read macOS network services')
    services = []
    name = None
    for line in result.stdout.splitlines():
        match = re.match(r'^\(\d+\) (.+)$', line)
        if match:
            name = match.group(1)
        elif name and re.search(r'Device: en\d+\)', line):
            services.append(name)
            name = None
    if not services:
        raise RuntimeError('No Wi-Fi or Ethernet services found')
    return services

SERVICES = []

def run(*args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if p.returncode or 'Error' in p.stdout or 'AuthorizationCreate' in p.stdout + p.stderr:
        raise RuntimeError((p.stdout + p.stderr).strip())
    return p.stdout.strip()

def get(service):
    text = run('/usr/sbin/networksetup', '-getdnsservers', service)
    if "There aren't any DNS Servers" in text:
        return []
    ips = text.splitlines()
    for ip in ips:
        ipaddress.ip_address(ip)
    return ips

def setdns(service, ips):
    run('/usr/sbin/networksetup', '-setdnsservers', service, *(ips or ['empty']))
    if get(service) != ips:
        raise RuntimeError('macOS did not apply DNS for: ' + service)

def save(data):
    write_json(STATE, data)

def remember():
    write_json(DESIRED, {s: get(s) for s in SERVICES})

def refresh(service, expected):
    # A no-op networksetup write does not invalidate stale VPN Dynamic Store DNS.
    # Force an actual configuration change and restore the intended value at once.
    temporary = [] if expected else ['127.0.0.1']
    try:
        setdns(service, temporary)
    finally:
        setdns(service, expected)

def main(action):
    global SERVICES
    SERVICES = physical_services()
    if action == 'status':
        for service in SERVICES:
            print(service + ': ' + ', '.join(get(service) or ['automatic (DHCP)']))
        return
    if action == 'on':
        answer = run('/usr/bin/dig', '@127.0.0.1', 'example.com', '+time=6', '+tries=1')
        if 'status: NOERROR' not in answer or 'ANSWER: 0' in answer:
            raise RuntimeError('SWPulse is not responding. DNS was not changed. Install or check the DNS service first.')
        backup = json.loads(STATE.read_text()) if STATE.exists() else {}
        original_backup = dict(backup)
        changed = []
        try:
            for service in SERVICES:
                current = get(service)
                if current == ['127.0.0.1']:
                    if service not in backup:
                        raise RuntimeError('Local DNS is configured without a backup: ' + service)
                    # VPN clients can leave stale dynamic DNS despite this saved value.
                    refresh(service, ['127.0.0.1'])
                    continue
                backup[service] = current
                save(backup)  # durable before changing network settings
                changed.append((service, current))
                setdns(service, ['127.0.0.1'])
        except Exception:
            failures = []
            for service, old in reversed(changed):
                try:
                    setdns(service, old)
                    if service in original_backup:
                        backup[service] = original_backup[service]
                    else:
                        backup.pop(service, None)
                except Exception:
                    failures.append(service)
            save(backup)
            if failures:
                raise RuntimeError('DNS rollback incomplete; saved recovery settings retained. Use Repair DNS or disable SWPulse.')
            raise
        print('SWPulse enabled. A VPN can override system DNS.')
    elif action == 'off':
        if not STATE.exists():
            print('No saved SWPulse changes.')
            return
        backup = json.loads(STATE.read_text())
        for service in list(backup):
            current = get(service)
            if current == ['127.0.0.1']:
                setdns(service, backup[service])
            else:
                print(service + ': DNS was changed elsewhere; keeping the current setting.')
            del backup[service]
            save(backup)
        print('SWPulse disabled. Previous DNS restored.')
    elif action == 'refresh':
        if not DESIRED.exists():
            return
        expected = json.loads(DESIRED.read_text())
        for service, ips in expected.items():
            # Respect manual settings changed outside this tool.
            if get(service) == ips:
                refresh(service, ips)
        print('DNS refreshed after VPN exit.')
    elif action == 'dhcp':
        # Explicit emergency recovery, preserving a separate snapshot.
        snapshot = {s: get(s) for s in SERVICES}
        write_json(BASE / 'before-dhcp.json', snapshot)
        for service in SERVICES:
            setdns(service, [])
        print('DNS set to automatic (DHCP). Availability depends on the network.')
    else:
        raise ValueError('Commands: on, off, status, dhcp, refresh')
    if action != 'refresh':
        remember()
    run('/usr/bin/dscacheutil', '-flushcache')

if __name__ == '__main__':
    try:
        private_storage()
        with (BASE / '.switch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main(sys.argv[1] if len(sys.argv) > 1 else 'status')
    except Exception as e:
        print('Error: ' + str(e), file=sys.stderr)
        raise SystemExit(1)
