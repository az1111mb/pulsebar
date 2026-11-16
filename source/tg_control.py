import fcntl
import json
import os
import plistlib
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlencode
from tg_common import BASE, LABEL, PLIST, RUNTIME, SETTINGS, load_config, settings, write_json

DOMAIN = f'gui/{os.getuid()}'
TARGET = DOMAIN + '/' + LABEL

def call(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.3):
            return True
    except OSError:
        return False

def status():
    c = load_config()
    service = call('/bin/launchctl', 'print', TARGET)
    running = service.returncode == 0 and 'state = running' in service.stdout
    runtime = json.loads(RUNTIME.read_text()) if RUNTIME.exists() else {}
    pid = re.search(r'(?m)^\s*pid = (\d+)\s*$', service.stdout)
    if not pid or runtime.get('pid') != int(pid.group(1)):
        runtime = {}
    return {'enabled': PLIST.exists(), 'running': running, 'listening': listening(c['port']) if running else False,
            'share': bool(settings().get('share')), 'lan': runtime.get('lan', []) if running else [],
            'errors': runtime.get('errors', []) if running else [], 'port': c['port']}

def main(action):
    c = load_config()
    if action == 'status':
        print(json.dumps(status()))
        return
    if action == 'on':
        st = status()
        if st['running'] and st['listening']:
            return
        if listening(c['port']):
            raise RuntimeError('Port is in use. Quit the standalone TG WS Proxy app and try again.')
        if call('/bin/launchctl', 'print', TARGET).returncode == 0:
            call('/bin/launchctl', 'bootout', TARGET)
        write_json(RUNTIME, {'lan': [], 'errors': []})
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        (BASE / 'tg-service.log').touch(mode=0o600, exist_ok=True)
        (BASE / 'tg-service.log').chmod(0o600)
        plist = {'Label': LABEL, 'ProgramArguments': [str(BASE / 'tg-venv/bin/python'), str(BASE / 'tg_runner.py')],
                 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5,
                 'StandardOutPath': str(BASE / 'tg-service.log'), 'StandardErrorPath': str(BASE / 'tg-service.log'),
                 'ProcessType': 'Background'}
        PLIST.write_bytes(plistlib.dumps(plist))
        p = call('/bin/launchctl', 'bootstrap', DOMAIN, str(PLIST))
        if p.returncode:
            raise RuntimeError(p.stderr.strip())
        call('/bin/launchctl', 'kickstart', TARGET)
        for _ in range(40):
            if listening(c['port']):
                print('TG WS Proxy enabled')
                return
            time.sleep(.25)
        call('/bin/launchctl', 'bootout', TARGET)
        PLIST.unlink(missing_ok=True)
        raise RuntimeError('Proxy failed to start. Check the TG WS Proxy log.')
    elif action == 'off':
        if call('/bin/launchctl', 'print', TARGET).returncode == 0:
            result = call('/bin/launchctl', 'bootout', TARGET)
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
        PLIST.unlink(missing_ok=True)
        print('TG WS Proxy disabled')
    elif action in ['share-on', 'share-off']:
        s = settings()
        s['share'] = action == 'share-on'
        write_json(SETTINGS, s)
        if status()['running']:
            for _ in range(30):
                st = status()
                if not s['share'] and not st['lan']:
                    break
                if s['share'] and (st['lan'] or st['errors']):
                    break
                time.sleep(.1)
            if not s['share'] and status()['lan']:
                raise RuntimeError('Sharing is set to off, but listeners have not closed. Disable TG WS Proxy to stop them immediately.')
            if s['share'] and status()['errors']:
                raise RuntimeError('Could not open a LAN listener. Check network availability and port conflicts.')
        print('LAN sharing ' + ('enabled' if s['share'] else 'disabled'))
    elif action in ['link-local', 'link-lan']:
        st = status()
        if not st['listening']:
            raise RuntimeError('Enable TG WS Proxy first')
        if action == 'link-lan':
            if not st['share'] or not st['lan']:
                raise RuntimeError('Enable LAN sharing and connect to Wi-Fi or Ethernet')
            host = st['lan'][0]
        else:
            host = '127.0.0.1'
        secret = 'dd' + c['secret']
        if c.get('fake_tls_domain'):
            secret = 'ee' + c['secret'] + c['fake_tls_domain'].encode('ascii').hex()
        print('tg://proxy?' + urlencode({'server': host, 'port': c['port'], 'secret': secret}))
    else:
        raise ValueError('Unknown command')

if __name__ == '__main__':
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        with (BASE / '.tg-switch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            main(sys.argv[1] if len(sys.argv) > 1 else 'status')
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
