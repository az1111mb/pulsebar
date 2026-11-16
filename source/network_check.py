#!/opt/homebrew/bin/python3
"""Bounded, offline-capable macOS DNS/HTTPS diagnostics. No settings are changed."""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import subprocess
import time
from tg_common import write_json

BASE = pathlib.Path(__file__).resolve().parent

def run(args, timeout=18):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {'exit': p.returncode, 'text': (p.stdout + p.stderr).strip()}
    except subprocess.TimeoutExpired:
        return {'exit': 124, 'text': 'TIMEOUT'}
    except OSError as e:
        return {'exit': 127, 'text': str(e)}

def route(ip):
    r = run(['/sbin/route', '-n', 'get', ip])
    m = re.search(r'interface:\s*(\S+)', r['text'])
    return m.group(1) if m else 'unknown'

def snapshot():
    return {ip: route(ip) for ip in ['1.1.1.1', '45.134.218.34', '8.8.8.8']}

def vpn(s):
    return any(v.startswith(('utun', 'ppp', 'ipsec')) for v in s.values())

def curl(url, extra=()):
    return run(['/usr/bin/curl', '--noproxy', '*', '--connect-timeout', '5',
                '--max-time', '12', '-sS', *extra, url], 15)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wait-no-vpn', action='store_true')
    ap.add_argument('--port', default='53')
    args = ap.parse_args()
    if args.wait_no_vpn:
        print('Disconnect your VPN. Waiting up to 5 minutes; results will be saved locally.', flush=True)
        until = time.monotonic() + 300
        while vpn(snapshot()) and time.monotonic() < until:
            time.sleep(2)
        if vpn(snapshot()):
            print('VPN is still enabled; the direct connection test was not performed.')
            return 2
    before = snapshot()
    print('Starting test. Routes:', before, flush=True)
    default_route = run(['/sbin/route', '-n', 'get', 'default'])['text']
    match = re.search(r'interface:\s*(en\d+)', default_route)
    physical = match.group(1) if match else 'en0'
    jobs = {
        'system_dns': ['/usr/sbin/scutil', '--dns'],
        'system_proxy': ['/usr/sbin/scutil', '--proxy'],
        'vpn_connections': ['/usr/sbin/scutil', '--nc', 'list'],
        'routes': ['/usr/sbin/netstat', '-rn', '-f', 'inet'],
        'wifi_dns': ['/usr/sbin/networksetup', '-getdnsservers', 'Wi-Fi'],
        'dhcp': ['/usr/sbin/ipconfig', 'getpacket', physical],
    }
    dhcp_dns = run(['/usr/sbin/ipconfig', 'getoption', physical, 'domain_name_server'])['text'].split()
    servers = ['1.1.1.1', '1.0.0.1', '8.8.8.8'] + [ip for ip in dhcp_dns if re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}', ip)]
    for server in dict.fromkeys(servers):
        jobs['dns_' + server] = ['/usr/bin/dig', '@' + server, 'example.com', '+time=3', '+tries=1']
    for domain in ['example.com', 'chatgpt.com', 'api.openai.com']:
        jobs['local_' + domain] = ['/usr/bin/dig', '@127.0.0.1', '-p', args.port, domain, '+time=7', '+tries=1']
        jobs['system_' + domain] = ['/usr/bin/dscacheutil', '-q', 'host', '-a', 'name', domain]
        jobs['https_' + domain] = ['/usr/bin/curl', '--noproxy', '*', '--connect-timeout', '5', '--max-time', '12', '-sS', '-o', '/dev/null', '-w', 'HTTP=%{http_code} IP=%{remote_ip} TLS=%{ssl_verify_result}\n', 'https://' + domain + '/']
    jobs['swpulse_tls'] = ['/usr/bin/curl', '--noproxy', '*', '--connect-timeout', '5', '--max-time', '12', '--resolve', 'dns.swpulse.ru:443:45.134.218.34', '-sS', '-o', '/dev/null', '-w', 'HTTP=%{http_code} TLS=%{ssl_verify_result}\n', 'https://dns.swpulse.ru/dns-query']
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(run, cmd): name for name, cmd in jobs.items()}
        for f in concurrent.futures.as_completed(futures):
            name = futures[f]
            results[name] = f.result()
            print(name + ': ' + results[name]['text'][:160].replace('\n', ' '), flush=True)
    # Official SWPulse challenge, resolved through the macOS resolver (not dig).
    try:
        start = curl('https://swpulse.ru/api/dns-check/start')
        probe = json.loads(start['text'])
        host, token = probe['host'], probe['token']
        if not re.fullmatch(r'[a-zA-Z0-9.-]+', host) or not re.fullmatch(r'[a-zA-Z0-9_-]+', token):
            raise ValueError('Unexpected challenge format')
        results['swpulse_probe_dns'] = run(['/usr/bin/dscacheutil', '-q', 'host', '-a', 'name', host], 12)
        for _ in range(3):
            response = curl('https://swpulse.ru/api/dns-check/status?token=' + token)
            status = json.loads(response['text'])
            if status.get('via'):
                break
            time.sleep(1)
        results['swpulse_system_check'] = status
    except (ValueError, KeyError) as e:
        results['swpulse_system_check'] = {'error': str(e)}
    after = snapshot()
    clean = not vpn(before) and not vpn(after) and 'unknown' not in [*before.values(), *after.values()]
    summary = 'No VPN route detected at the start or end of the test.' if clean else 'Direct connection NOT confirmed: a tunnel or unknown route was detected.'
    summary += '\nHTTP 403/401 indicates a server response, not successful ChatGPT login.'
    report = {'time': datetime.datetime.now().astimezone().isoformat(), 'summary': summary,
              'routes_before': before, 'routes_after': after, 'results': results}
    folder = BASE / 'reports'
    folder.mkdir(exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    path = folder / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
    write_json(path, report)
    write_json(folder / 'latest.json', report)
    print('\n' + summary + '\nSWPulse: ' + str(results['swpulse_system_check']) + '\nReport: ' + str(path), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
