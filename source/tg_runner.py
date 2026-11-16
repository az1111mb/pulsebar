"""Official TG WS backend plus opt-in forwarding on physical LAN addresses."""
import asyncio
import contextlib
import ipaddress
import logging
import logging.handlers
import os
import re
import signal
import sys
from tg_common import BASE, RUNTIME, PRIVATE_NETWORKS, lan_interfaces, load_config, settings, write_json

sys.path.insert(0, str(BASE / 'tg-source'))
class RedactingFormatter(logging.Formatter):
    def __init__(self, secret):
        super().__init__('%(asctime)s %(levelname)s %(message)s')
        self.secret = secret

    def format(self, record):
        text = super().format(record)
        text = re.sub(re.escape(self.secret), '[REDACTED]', text, flags=re.I)
        text = re.sub(r'tg://\S+', '[REDACTED PROXY LINK]', text)
        text = re.sub(r'(?i)(secret[\s\"\x27:=]+)\S+', r'\1[REDACTED]', text)
        return text

def configure():
    from proxy.config import proxy_config, parse_dc_ip_list, coerce_domain_list
    c = load_config()
    proxy_config.host = '127.0.0.1'
    proxy_config.port = int(c['port'])
    proxy_config.secret = c['secret']
    proxy_config.dc_redirects = parse_dc_ip_list(c.get('dc_ip', ['2:149.154.167.220', '4:149.154.167.220']))
    proxy_config.buffer_size = max(4, int(c.get('buf_kb', 256))) * 1024
    proxy_config.pool_size = max(0, int(c.get('pool_size', 4)))
    proxy_config.fallback_cfproxy = bool(c.get('cfproxy', True))
    proxy_config.cfproxy_h2_media = bool(c.get('h2', True))
    proxy_config.cfproxy_user_domains = coerce_domain_list(c.get('cfproxy_user_domain', [])) if c.get('cfproxy_user_domain_enabled') else []
    proxy_config.cfproxy_worker_domains = coerce_domain_list(c.get('cfproxy_worker_domain', [])) if c.get('cfproxy_worker_enabled') else []
    proxy_config.disable_secure = bool(c.get('no_secure', False))
    proxy_config.fake_tls_domain = c.get('fake_tls_domain', '')
    proxy_config.force_test_dc = bool(c.get('force_test_dc', False))
    handler = logging.handlers.RotatingFileHandler(BASE / 'tg-proxy.log', maxBytes=2_000_000, backupCount=1)
    (BASE / 'tg-proxy.log').chmod(0o600)
    handler.setFormatter(RedactingFormatter(c['secret']))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    for name in ['httpx', 'httpcore', 'asyncio']:
        logging.getLogger(name).setLevel(logging.WARNING)
    return proxy_config

class LANForwarder:
    def __init__(self, port):
        self.port = port
        self.servers = {}
        self.connections = set()
        self.bindings = {}

    async def relay(self, reader, writer, address, network):
        peer = writer.get_extra_info('peername')
        ip = ipaddress.ip_address(peer[0]) if peer else None
        if (self.bindings.get(address) != network or not ip or
                not any(ip in private for private in PRIVATE_NETWORKS) or
                ip not in ipaddress.ip_network(network) or len(self.connections) >= 128):
            writer.close()
            return
        task = asyncio.current_task()
        self.connections.add(task)
        upstream = None
        pipes = []
        async def copy(source, dest):
            while data := await source.read(65536):
                dest.write(data)
                await dest.drain()
        try:
            remote, upstream = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', self.port), 5)
            pipes = [asyncio.create_task(copy(reader, upstream)), asyncio.create_task(copy(remote, writer))]
            await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            for pipe in pipes:
                pipe.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            for stream in [writer, upstream]:
                if stream:
                    stream.close()
                    with contextlib.suppress(Exception):
                        await stream.wait_closed()
            self.connections.discard(task)

    async def close_connections(self):
        tasks = list(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self):
        previous = None
        try:
            while True:
                desired = await asyncio.to_thread(lan_interfaces) if settings().get('share') else {}
                errors = []
                changed = self.bindings != desired
                # Revoke admission before closing sockets and cancelling existing relays.
                self.bindings = dict(desired)
                for address in list(self.servers):
                    if changed:
                        server = self.servers.pop(address)
                        server.close()
                        await server.wait_closed()
                if changed:
                    await self.close_connections()
                for address, network in desired.items():
                    if address not in self.servers:
                        try:
                            self.servers[address] = await asyncio.start_server(lambda r, w, a=address, n=network: self.relay(r, w, a, n), address, self.port)
                        except OSError as e:
                            errors.append(str(e))
                status = {'lan': list(self.servers), 'errors': errors, 'pid': os.getpid()}
                if status != previous:
                    write_json(RUNTIME, status)
                    previous = status
                await asyncio.sleep(1)
        finally:
            self.bindings = {}
            for server in self.servers.values():
                server.close()
                await server.wait_closed()
            await self.close_connections()
            write_json(RUNTIME, {'lan': [], 'errors': []})

async def main():
    os.umask(0o077)
    from proxy.tg_ws_proxy import _run
    proxy_config = configure()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    forwarder = LANForwarder(proxy_config.port)
    sharing = asyncio.create_task(forwarder.run())
    try:
        await _run(stopped)
    finally:
        sharing.cancel()
        await asyncio.gather(sharing, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
