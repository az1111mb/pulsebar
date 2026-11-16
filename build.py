#!/usr/bin/env python3
"""Build the menu app locally and fetch current official stable releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import uuid
import tomllib
import urllib.parse

HERE = Path(__file__).resolve().parent
WORK = HERE / '.build'
SOURCE = HERE / 'source'
SUPPORT = Path.home() / 'Library/Application Support/SWPulse'

def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def download(url, destination):
    temporary = Path(str(destination) + '.part')
    run('/usr/bin/curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2',
        '--proto', '=https', '--proto-redir', '=https', '--connect-timeout', '15', '--max-time', '180', '-H', 'User-Agent: SWPulse-menu-builder',
        url, '-o', temporary)
    temporary.replace(destination)

def release(repo):
    path = WORK / (repo.split('/')[-1] + '-release.json')
    download('https://api.github.com/repos/' + repo + '/releases/latest', path)
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plist(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(value))

def extract(archive, destination):
    destination.mkdir(exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(destination, filter='data')

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def activate(app, dns, tg_source, requirements, manifest):
    SUPPORT.mkdir(parents=True, exist_ok=True, mode=0o700)
    SUPPORT.chmod(0o700)
    agents = Path.home() / 'Library/LaunchAgents'
    agents.mkdir(parents=True, exist_ok=True)
    domain = f'gui/{os.getuid()}'
    # Preserve service enablement and all personal configuration files.
    active_tg = subprocess.run(['/bin/launchctl', 'print', domain + '/ru.swpulse.telegram'], capture_output=True).returncode == 0
    python_path = next((p for p in [Path('/opt/homebrew/bin/python3'), Path('/usr/local/bin/python3')] if p.exists()), Path(sys.executable))
    # Prepare dependencies before replacing running components.
    venv = SUPPORT / 'runtimes' / uuid.uuid4().hex
    venv.parent.mkdir(exist_ok=True, mode=0o700)
    run(python_path, '-m', 'venv', venv)
    run(venv / 'bin/python', '-m', 'pip', 'install', '--upgrade', *requirements)
    run(venv / 'bin/python', '-c', 'from proxy.config import proxy_config; from proxy.tg_ws_proxy import _run', cwd=tg_source)
    if active_tg:
        run('/bin/launchctl', 'bootout', domain + '/ru.swpulse.telegram')
    subprocess.run(['/bin/launchctl', 'bootout', domain + '/ru.swpulse.dns-guard'], capture_output=True)
    old_venv = SUPPORT / 'tg-venv'
    if old_venv.is_symlink():
        old_venv.unlink()
    elif old_venv.exists():
        old_venv.rename(venv.parent / ('previous-' + uuid.uuid4().hex))
    old_venv.symlink_to(venv, target_is_directory=True)
    for name in ['swpulse.py', 'network_check.py', 'dns_guard.py', 'tg_common.py', 'tg_runner.py', 'tg_control.py', 'health.py']:
        copy(SOURCE / name, SUPPORT / name)
    (SUPPORT / 'python-path.txt').write_text(str(python_path))
    target_source = SUPPORT / 'tg-source'
    target_source.mkdir(exist_ok=True)
    proxy_dir = target_source / 'proxy'
    if proxy_dir.exists():
        previous = target_source / 'proxy.previous'
        if previous.exists():
            shutil.rmtree(previous)
        proxy_dir.rename(previous)
    shutil.copytree(tg_source / 'proxy', proxy_dir)
    copy(tg_source / 'LICENSE', target_source / 'LICENSE')

    daemon = {
        'Label': 'ru.swpulse.local-dns',
        'ProgramArguments': ['/usr/local/libexec/swpulse/dnsproxy', '--listen', '127.0.0.1', '--port', '53',
                             '--upstream', 'sdns://AgAAAAAAAAAADTQ1LjEzNC4yMTguMzQADmRucy5zd3B1bHNlLnJ1Ci9kbnMtcXVlcnk', '--timeout', '6s', '--cache'],
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5,
        'StandardOutPath': '/var/log/swpulse-dns.log', 'StandardErrorPath': '/var/log/swpulse-dns.log', 'ProcessType': 'Background'}
    daemon_file = WORK / 'ru.swpulse.local-dns.plist'
    plist(daemon_file, daemon)
    installed_binary = Path('/usr/local/libexec/swpulse/dnsproxy')
    installed_plist = Path('/Library/LaunchDaemons/ru.swpulse.local-dns.plist')
    same = installed_binary.exists() and installed_plist.exists() and sha(installed_binary) == sha(dns) and plistlib.loads(installed_plist.read_bytes()) == daemon
    if not same:
        print('macOS needs an administrator password for the DNS service. Enter it locally in Terminal.', flush=True)
        run('/usr/bin/sudo', '/bin/bash', HERE / 'install-dns.sh', dns, daemon_file)
    elif subprocess.run(['/bin/launchctl', 'print', 'system/ru.swpulse.local-dns'], capture_output=True).returncode:
        run('/usr/bin/sudo', '/bin/launchctl', 'bootstrap', 'system', installed_plist)

    app_target = Path.home() / 'Applications/SWPulse.app'
    app_target.parent.mkdir(exist_ok=True)
    executable = str(app_target / 'Contents/MacOS/SWPulse')
    running = subprocess.run(['/usr/bin/pgrep', '-f', '^' + re.escape(executable) + '$'], capture_output=True, text=True)
    for pid in running.stdout.split():
        os.kill(int(pid), signal.SIGTERM)
    if app_target.exists():
        backup = WORK / 'previous-SWPulse.app'
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(app_target, backup)
    shutil.copytree(app, app_target)
    guard = {'Label': 'ru.swpulse.dns-guard', 'ProgramArguments': [str(python_path), str(SUPPORT / 'dns_guard.py')],
             'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5, 'ProcessType': 'Background',
             'StandardOutPath': str(Path.home() / 'Library/Logs/SWPulse-dns-guard.log'),
             'StandardErrorPath': str(Path.home() / 'Library/Logs/SWPulse-dns-guard.log')}
    plist(agents / 'ru.swpulse.dns-guard.plist', guard)
    run('/bin/launchctl', 'bootstrap', domain, agents / 'ru.swpulse.dns-guard.plist')
    run('/bin/launchctl', 'kickstart', domain + '/ru.swpulse.dns-guard')
    if not (SUPPORT / 'versions.json').exists() or (agents / 'ru.swpulse.menubar.plist').exists():
        plist(agents / 'ru.swpulse.menubar.plist', {'Label': 'ru.swpulse.menubar', 'ProgramArguments': ['/usr/bin/open', '-g', str(app_target)], 'RunAtLoad': True})
    (SUPPORT / 'versions.json').write_text(json.dumps(manifest, indent=2))
    if active_tg:
        run(python_path, SUPPORT / 'tg_control.py', 'on')
    run('/usr/bin/open', app_target)
    print('Ready. Look for 0_0 or -.- in the menu bar. Local settings were preserved.', flush=True)

def install(app, dns, tg_source, requirements, manifest):
    """Rollback user-space managed files and service enablement on activation errors."""
    SUPPORT.mkdir(parents=True, exist_ok=True, mode=0o700)
    SUPPORT.chmod(0o700)
    agents = Path.home() / 'Library/LaunchAgents'
    domain = f'gui/{os.getuid()}'
    labels = ['ru.swpulse.telegram', 'ru.swpulse.dns-guard']
    active = {label: subprocess.run(['/bin/launchctl', 'print', domain + '/' + label], capture_output=True).returncode == 0 for label in labels}
    managed = [SUPPORT / name for name in ['swpulse.py', 'network_check.py', 'dns_guard.py', 'tg_common.py', 'tg_runner.py', 'tg_control.py', 'health.py', 'python-path.txt', 'versions.json', 'tg-source', 'tg-venv']]
    managed += [agents / (label + '.plist') for label in labels + ['ru.swpulse.menubar']]
    managed += [Path.home() / 'Applications/SWPulse.app']
    def restore_copy(src, dst):
        if src.is_symlink():
            dst.symlink_to(src.readlink(), target_is_directory=True)
        elif src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            copy(src, dst)
    with tempfile.TemporaryDirectory(prefix='.rollback-', dir=SUPPORT) as temporary:
        saved = Path(temporary)
        for i, target in enumerate(managed):
            if target.exists() or target.is_symlink():
                restore_copy(target, saved / str(i))
        try:
            activate(app, dns, tg_source, requirements, manifest)
        except BaseException:
            for label in labels:
                subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + label], capture_output=True)
            for i, target in enumerate(managed):
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.exists():
                    shutil.rmtree(target)
                backup = saved / str(i)
                if backup.exists() or backup.is_symlink():
                    restore_copy(backup, target)
            for label, was_active in active.items():
                if was_active:
                    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(agents / (label + '.plist'))], capture_output=True)
            print('Installation failed. Previous user-space files and service settings restored.', file=sys.stderr)
            raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-only', action='store_true')
    args = ap.parse_args()
    if platform.system() != 'Darwin':
        raise RuntimeError('This kit requires macOS')
    run('/usr/bin/xcrun', '--find', 'swiftc', stdout=subprocess.DEVNULL)
    arch = platform.machine()
    if arch not in ['arm64', 'x86_64']:
        raise RuntimeError('Apple Silicon and Intel Mac are supported')
    WORK.mkdir(exist_ok=True)
    print('Fetching the latest stable releases from official GitHub repositories...', flush=True)
    dns_release = release('AdguardTeam/dnsproxy')
    dns_arch = 'arm64' if arch == 'arm64' else 'amd64'
    assets = [a for a in dns_release['assets'] if a['name'].startswith('dnsproxy-darwin-' + dns_arch + '-') and a['name'].endswith('.tar.gz')]
    if len(assets) != 1:
        raise RuntimeError('Could not identify a unique dnsproxy release for this Mac')
    asset = assets[0]
    digest = asset.get('digest', '')
    if not digest.startswith('sha256:'):
        raise RuntimeError('GitHub did not provide a dnsproxy SHA-256 digest; installation stopped')
    archive = WORK / asset['name']
    if not archive.exists() or sha(archive) != digest[7:]:
        download(asset['browser_download_url'], archive)
    if sha(archive) != digest[7:]:
        raise RuntimeError('dnsproxy SHA-256 verification failed')
    dns_dir = WORK / ('dns-' + dns_release['tag_name'])
    extract(archive, dns_dir)
    dns = next(p for p in dns_dir.rglob('dnsproxy') if p.is_file())

    tg_release = release('Flowseal/tg-ws-proxy')
    tag = tg_release['tag_name']
    tg_archive = WORK / ('tg-' + re.sub(r'[^a-zA-Z0-9._-]', '_', tag) + '.tar.gz')
    download('https://api.github.com/repos/Flowseal/tg-ws-proxy/tarball/' + urllib.parse.quote(tag, safe=''), tg_archive)
    tg_dir = WORK / ('tg-' + re.sub(r'[^a-zA-Z0-9._-]', '_', tag) + '-' + sha(tg_archive)[:12])
    extract(tg_archive, tg_dir)
    tg_source = next(p.parent for p in tg_dir.glob('*/pyproject.toml'))
    project = tomllib.loads((tg_source / 'pyproject.toml').read_text())
    core = {'httpx', 'cryptography', 'certifi', 'psutil'}
    requirements = [r for r in project['project']['dependencies'] if re.match(r'^[A-Za-z0-9_-]+', r).group().lower() in core]
    # Verify the integration API before replacing any existing installation.
    backend = (tg_source / 'proxy/tg_ws_proxy.py').read_text()
    if 'async def _run(' not in backend:
        raise RuntimeError('TG WS Proxy changed its integration API; update the wrapper before installing')
    manifest = {'dnsproxy': dns_release['tag_name'], 'dnsproxy_sha256': sha(archive),
                'tg_ws_proxy': tag, 'tg_source_sha256': sha(tg_archive), 'architecture': arch,
                'sources': ['https://github.com/AdguardTeam/dnsproxy', 'https://github.com/Flowseal/tg-ws-proxy']}
    (WORK / 'versions.json').write_text(json.dumps(manifest, indent=2))
    print('dnsproxy:', manifest['dnsproxy'], 'TG WS Proxy:', tag, flush=True)

    app = WORK / 'SWPulse.app'
    contents = app / 'Contents'
    (contents / 'MacOS').mkdir(parents=True, exist_ok=True)
    (contents / 'Resources').mkdir(exist_ok=True)
    cache = WORK / 'swift-cache'
    run('/usr/bin/xcrun', 'swiftc', SOURCE / 'Pulsebar.swift', '-o', contents / 'MacOS/SWPulse',
        '-framework', 'AppKit', '-framework', 'CoreImage', '-module-cache-path', cache, '-O', '-target', arch + '-apple-macosx14.0')
    iconset = WORK / 'AppIcon.iconset'
    run('/usr/bin/xcrun', 'swift', '-module-cache-path', cache, SOURCE / 'Icon.swift', iconset)
    run('/usr/bin/iconutil', '-c', 'icns', iconset, '-o', contents / 'Resources/AppIcon.icns')
    plist(contents / 'Info.plist', {'CFBundleExecutable': 'SWPulse', 'CFBundleIdentifier': 'ru.swpulse.menubar',
          'CFBundleName': 'Pulsebar', 'CFBundleDisplayName': 'Pulsebar',
          'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '2.2', 'CFBundleVersion': '4',
          'LSUIElement': True, 'LSMinimumSystemVersion': '14.0', 'NSHighResolutionCapable': True, 'CFBundleIconFile': 'AppIcon'})
    run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', app)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
    if args.build_only:
        print('Build ready:', app)
    else:
        install(app, dns, tg_source, requirements, manifest)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Error:', e, file=sys.stderr)
        raise SystemExit(1)
