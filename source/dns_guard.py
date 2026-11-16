#!/opt/homebrew/bin/python3
"""Refresh managed DNS after VPN exit, without changing an active VPN."""
import datetime
import pathlib
import subprocess
import time
import sys
from network_check import snapshot, vpn

BASE = pathlib.Path(__file__).resolve().parent
previous = None
while True:
    try:
        routes = snapshot()
        if 'unknown' not in routes.values():
            connected = vpn(routes)
            if not connected and previous is not False:
                # Let the VPN finish restoring its saved (possibly stale) DNS.
                time.sleep(1)
                if not vpn(snapshot()):
                    p = subprocess.run([sys.executable, str(BASE / 'swpulse.py'), 'refresh'],
                                       capture_output=True, text=True, timeout=30)
                    print(datetime.datetime.now().isoformat(), p.returncode, p.stdout, p.stderr, flush=True)
                    if p.returncode:
                        time.sleep(2)
                        continue
            previous = connected
    except Exception as e:
        print(datetime.datetime.now().isoformat(), str(e), flush=True)
    time.sleep(2)
