"""Bounded connectivity checks, with no Telegram login or message access."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from tg_common import BASE, load_config, write_json

def telegram_probe(host, port, secret, dc=2):
    deadline = time.monotonic() + 8
    while True:
        init = bytearray(os.urandom(64))
        if init[0] not in (0xef, 0x16) and init[:4] not in [b'HEAD', b'POST', b'GET ', b'OPTI', b'\xdd'*4, b'\xee'*4] and init[4:8] != bytes(4):
            break
    init[56:60] = b'\xdd'*4
    init[60:62] = struct.pack('<h', dc)
    reverse = init[::-1]
    encrypt = Cipher(algorithms.AES(hashlib.sha256(init[8:40] + secret).digest()), modes.CTR(bytes(init[40:56]))).encryptor()
    decrypt = Cipher(algorithms.AES(hashlib.sha256(reverse[8:40] + secret).digest()), modes.CTR(bytes(reverse[40:56]))).decryptor()
    encrypted = encrypt.update(bytes(init))
    nonce = os.urandom(16)
    body = struct.pack('<I', 0xbe7e8ef1) + nonce
    payload = bytes(8) + struct.pack('<QI', int(time.time() * 2**32) & ~3, len(body)) + body
    padding = os.urandom(4)
    frame = struct.pack('<I', len(payload) + len(padding)) + payload + padding
    with socket.create_connection((host, port), timeout=8) as sock:
        sock.settimeout(8)
        sock.sendall(bytes(init[:56]) + encrypted[56:] + encrypt.update(frame))
        def read(n):
            data = b''
            while len(data) < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Telegram handshake timed out')
                sock.settimeout(remaining)
                part = sock.recv(n - len(data))
                if not part:
                    raise OSError('Proxy closed the connection')
                data += part
            return decrypt.update(data)
        length = struct.unpack('<I', read(4))[0]
        if not 40 <= length <= 65536:
            return False
        reply = read(length)
        return reply[20:24] == struct.pack('<I', 0x05162463) and reply[24:40] == nonce

def tg_check():
    try:
        c = load_config()
        if c.get('fake_tls_domain'):
            return {'ok': False, 'detail': 'This health check does not support Fake TLS'}
        ok = telegram_probe('127.0.0.1', int(c['port']), bytes.fromhex(c['secret']))
        return {'ok': ok, 'detail': 'Telegram handshake verified' if ok else 'Telegram did not return a valid handshake'}
    except Exception as e:
        return {'ok': False, 'detail': str(e)}

def dns_check(effective):
    if not effective:
        return {'ok': False, 'detail': 'System DNS is not using SWPulse'}
    try:
        name = os.urandom(8).hex() + '.example.com'
        p = subprocess.run(['/usr/bin/dig', '@127.0.0.1', name, '+time=4', '+tries=1'], capture_output=True, text=True, timeout=6)
        ok = p.returncode == 0 and any(s in p.stdout for s in ['status: NOERROR', 'status: NXDOMAIN'])
        return {'ok': ok, 'detail': 'Fresh DNS query succeeded' if ok else 'DNS query failed'}
    except Exception as e:
        return {'ok': False, 'detail': str(e)}

def main():
    flags = sorted(sys.argv[1:])
    cache = BASE / 'health.json'
    if cache.exists():
        try:
            old = json.loads(cache.read_text())
        except (ValueError, OSError):
            old = {}
        if old.get('flags') == flags and 0 <= time.time() - old.get('time', 0) < 20:
            print(json.dumps(old)); return
    result = {'time': time.time(), 'flags': flags}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {}
        if '--dns' in flags:
            jobs['dns'] = pool.submit(dns_check, '--effective' in flags)
        if '--tg' in flags:
            jobs['tg'] = pool.submit(tg_check)
        for key, future in jobs.items():
            result[key] = future.result()
    write_json(cache, result)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
