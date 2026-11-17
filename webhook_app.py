"""GitHub webhooks -> potpisani lokalni prijemnik -> Windows zvuk."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('git_sound')


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    for attempt in range(5):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def credential():
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN']
    result = subprocess.run(
        ['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
        text=True, capture_output=True, timeout=25,
        env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never'),
        creationflags=subprocess.CREATE_NO_WINDOW)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):
        raise RuntimeError('Nema GitHub prijave. Prijavi Git u GitHub ili postavi GITHUB_TOKEN.')
    return fields['password']


def account_owners(config, login):
    owners = config.get('owners') or [login]
    if {owner.casefold() for owner in owners} != {login.casefold()}:
        raise ValueError('owners mora biti prazan za automatski odabir ili odgovarati prijavljenom GitHub racunu.')
    return owners


class API:
    def __init__(self):
        self.token = credential()

    def call(self, path, method='GET', data=None):
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request('https://api.github.com' + path, data=body, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'User-Agent': 'GitSound',
                     'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    def pages(self, path):
        page = 1
        while True:
            batch = self.call(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            yield from batch
            if len(batch) < 100:
                break
            page += 1


class Receiver:
    def __init__(self, secret, owners, sounds, database):
        self.secret = secret.encode()
        self.owners = {owner.lower() for owner in owners}
        self.sounds = sounds
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, received REAL)')
        self.db.commit()

    def accept(self, headers, body):
        expected = 'sha256=' + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get('X-Hub-Signature-256', '')):
            return 401
        delivery = headers.get('X-GitHub-Delivery', '')
        if not delivery or len(delivery) > 200:
            return 400
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                return 400
        except (ValueError, UnicodeError):
            return 400
        event = headers.get('X-GitHub-Event', '')
        if event == 'ping':
            LOG.info('GitHub ping primljen i potpis provjeren.')
            return 200
        repo = data.get('repository') or {}
        if not isinstance(repo, dict):
            return 400
        full_name = repo.get('full_name', '')
        if not isinstance(full_name, str) or full_name.split('/')[0].lower() not in self.owners:
            return 403
        kind = {'push': 'push', 'fork': 'fork', 'star': 'star'}.get(event)
        if kind is None or (event == 'star' and data.get('action') != 'created'):
            return 200
        with self.lock:
            if self.db.execute('SELECT 1 FROM deliveries WHERE id=?', (delivery,)).fetchone():
                return 200
            if self.sounds.full():
                return 503
            self.db.execute('INSERT INTO deliveries VALUES (?, ?)', (delivery, time.time()))
            self.db.execute('DELETE FROM deliveries WHERE received < ?', (time.time() - 30 * 86400,))
            self.db.commit()
            self.sounds.put_nowait(kind)
        LOG.info('WEBHOOK %s | %s', kind, full_name)
        return 200


def handler_for(receiver):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, code):
            self.send_response(code)
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404)

        def do_POST(self):
            if self.path != '/github':
                self.reply(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 < length <= 26 * 1024 * 1024:
                    self.reply(413)
                    return
                body = self.rfile.read(length)
                self.reply(receiver.accept(self.headers, body))
            except (ValueError, TimeoutError):
                self.reply(400)
            except Exception:
                LOG.exception('Greska obrade webhooka')
                self.reply(500)

        def log_message(self, *args):
            pass
    return Handler


def synchronize(api, config, url, secret):
    login = api.call('/user')['login']
    owners = {owner.lower() for owner in account_owners(config, login)}
    registry_path = ROOT / 'webhook_registry.json'
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    succeeded, failed = [], []
    repos = list(api.pages('/user/repos?visibility=all&affiliation=owner&sort=full_name'))
    for repo in repos:
        name = repo['full_name']
        if name.split('/')[0].lower() not in owners:
            continue
        if not repo.get('permissions', {}).get('admin'):
            failed.append({'repo': name, 'reason': 'Nema admin ovlasti'})
            continue
        payload = {'name': 'web', 'active': True, 'events': ['push', 'star', 'fork'],
                   'config': {'url': url + '/github', 'content_type': 'json', 'secret': secret, 'insecure_ssl': '0'}}
        try:
            hook_id = registry.get(name)
            if hook_id:
                try:
                    api.call(f'/repos/{name}/hooks/{hook_id}', 'PATCH', payload)
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
                    hook_id = None
            if not hook_id:
                # Ne diramo korisnikove druge webhookove.
                existing = next((h for h in api.pages(f'/repos/{name}/hooks')
                                 if h.get('config', {}).get('url') == url + '/github'), None)
                if existing:
                    hook_id = existing['id']
                    api.call(f'/repos/{name}/hooks/{hook_id}', 'PATCH', payload)
                else:
                    hook_id = api.call(f'/repos/{name}/hooks', 'POST', payload)['id']
            registry[name] = hook_id
            atomic_json(registry_path, registry)
            succeeded.append({'repo': name, 'private': repo['private']})
        except urllib.error.HTTPError as exc:
            failed.append({'repo': name, 'reason': 'GitHub HTTP ' + str(exc.code)})
            LOG.warning('Webhook %s nije postavljen: HTTP %s', name, exc.code)
    status = {'url': url + '/github', 'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
              'configured': succeeded, 'failed': failed}
    atomic_json(ROOT / 'webhook_status.json', status)
    LOG.info('Webhookovi spremni: %s javnih, %s privatnih, %s neuspjelih.',
             sum(not r['private'] for r in succeeded), sum(r['private'] for r in succeeded), len(failed))
    return status


def read_tunnel_output(stream, log_path, urls, connected, failed):
    with log_path.open('w', encoding='utf-8') as log:
        for line in stream:
            log.write(line)
            log.flush()
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                urls.put(match.group(0))
            if 'Registered tunnel connection' in line and not failed.is_set():
                connected.set()
            if 'tunnel not found' in line.casefold() or 'unauthorized' in line.casefold():
                if not failed.is_set():
                    LOG.warning('Cloudflare je ponistio tunel; otvaram novu vezu.')
                connected.clear()
                failed.set()


def run(config):
    from git_sound import play, load_config
    api = API()
    owners = account_owners(config, api.call('/user')['login'])
    secret_path = ROOT / '.webhook-secret'
    if not secret_path.exists():
        secret_path.write_text(secrets.token_hex(32), encoding='ascii')
    secret = secret_path.read_text(encoding='ascii').strip()
    sounds = queue.Queue(maxsize=30)
    stop = threading.Event()
    receiver = Receiver(secret, owners, sounds, ROOT / 'deliveries.sqlite3')
    server = ThreadingHTTPServer(('127.0.0.1', int(config.get('webhook_port', 8765))), handler_for(receiver))
    server.daemon_threads = True
    def worker():
        while not stop.is_set():
            try:
                kind = sounds.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                play(load_config(), kind, stop)
            except Exception:
                LOG.exception('Reprodukcija nije uspjela')
            finally:
                sounds.task_done()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url_queue = queue.Queue()
    connected = threading.Event()
    tunnel_failed = threading.Event()
    tunnel_path = ROOT / 'bin' / 'cloudflared.exe'
    if not tunnel_path.is_file():
        server.shutdown()
        server.server_close()
        stop.set()
        receiver.db.close()
        raise RuntimeError('cloudflared nije instaliran. Pokreni INSTALL.bat.')
    tunnel = subprocess.Popen([str(tunnel_path), 'tunnel', '--no-autoupdate',
        '--protocol', 'http2', '--url', f'http://127.0.0.1:{server.server_port}'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW)
    threading.Thread(target=read_tunnel_output, args=(tunnel.stdout, ROOT / 'tunnel.log',
                     url_queue, connected, tunnel_failed), daemon=True).start()
    try:
        url = url_queue.get(timeout=90)
        LOG.info('HTTPS tunel: %s', url)
        # The edge connection is authoritative. Local DNS/certificate settings can
        # block a loop through the public hostname even when GitHub can reach it.
        deadline = time.monotonic() + 90
        while not connected.wait(timeout=0.5):
            if tunnel_failed.is_set() or tunnel.poll() is not None or time.monotonic() >= deadline:
                break
        if not connected.is_set() or tunnel_failed.is_set():
            raise RuntimeError('HTTPS tunel nije povezan; pogledaj tunnel.log.')
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/health', timeout=5) as response:
            if response.status != 200:
                raise RuntimeError('Lokalni webhook prijemnik nije dostupan.')
        while tunnel.poll() is None and not tunnel_failed.is_set():
            try:
                synchronize(api, config, url, secret)
            except Exception:
                LOG.exception('Sinkronizacija webhookova nije uspjela; ponovni pokusaj za 15 minuta.')
            for _ in range(180):
                if tunnel_failed.wait(5) or stop.is_set() or tunnel.poll() is not None:
                    break
        raise RuntimeError('HTTPS tunel je prekinut ili ponisten. Automatski slijedi novi pokusaj.')
    finally:
        stop.set()
        tunnel.terminate()
        tunnel.wait(timeout=10)
        server.shutdown()
        server.server_close()
        receiver.db.close()


if __name__ == '__main__':
    raise SystemExit('Pokreni git_sound.py ili START_BACKGROUND.bat.')
