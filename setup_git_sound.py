"""First-run setup. Python standard library only; Windows 10/11."""
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import struct
import sys
import urllib.request
import wave

ROOT = Path(__file__).resolve().parent


def create_defaults():
    folder = ROOT / 'sounds' / 'defaults'
    folder.mkdir(parents=True, exist_ok=True)
    melodies = {'push': [392, 494, 587, 784], 'star': [523, 659, 784, 1047],
                'fork': [659, 587, 784, 988]}
    for kind, notes in melodies.items():
        target = folder / (kind + '.wav')
        if target.exists():
            continue
        with wave.open(str(target), 'wb') as audio:
            audio.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            samples = bytearray()
            for frequency in notes:
                for index in range(13230):
                    t = index / 22050
                    envelope = min(1, t / 0.02) * max(0, 1 - t / 0.6)
                    value = int(7000 * envelope * math.sin(2 * math.pi * frequency * t))
                    samples.extend(struct.pack('<h', value))
            audio.writeframes(samples)


def install_cloudflared(token=None):
    target = ROOT / 'bin' / 'cloudflared.exe'
    if target.exists():
        print('cloudflared is already installed.')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    machine = platform.machine().lower()
    architecture = {'amd64': 'amd64', 'x86_64': 'amd64', 'arm64': 'arm64',
                    'aarch64': 'arm64', 'x86': '386', 'i386': '386'}.get(machine)
    if not architecture:
        raise RuntimeError('Unsupported Windows architecture: ' + machine)
    headers = {'User-Agent': 'GitSound-Setup', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('https://api.github.com/repos/cloudflare/cloudflared/releases/latest', headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset_name = f'cloudflared-windows-{architecture}.exe'
    asset = next((item for item in release['assets'] if item['name'] == asset_name), None)
    if asset is None:
        raise RuntimeError('Cloudflare does not provide ' + asset_name + ' in this release.')
    expected = asset.get('digest', '')
    if not expected.startswith('sha256:'):
        raise RuntimeError('Release has no SHA256 checksum; download manually from Cloudflare.')
    print('Downloading cloudflared ' + release['tag_name'] + '...')
    temporary = target.with_suffix('.download')
    try:
        urllib.request.urlretrieve(asset['browser_download_url'], temporary)
        actual = 'sha256:' + hashlib.sha256(temporary.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError('cloudflared checksum verification failed.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print('cloudflared SHA256 verified.')


def main():
    if os.name != 'nt':
        raise SystemExit('Git Sound currently supports Windows 10/11 only.')
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or later is required.')
    config = ROOT / 'config.json'
    if not config.exists():
        shutil.copyfile(ROOT / 'config.example.json', config)
    create_defaults()
    from webhook_app import API, credential
    token = credential()
    api = API()
    account = api.call('/user')['login']
    install_cloudflared(token)
    print('GitHub account: ' + account)
    print('Ready. Run START_BACKGROUND.bat (background) or START.bat (console).')
    print('Webhooks will be installed on your owned public and private repositories.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Setup failed: ' + str(exc))
        print('Authenticate Git for github.com using Git Credential Manager, or set GITHUB_TOKEN.')
        raise SystemExit(1)
