"""Git Sound: Windows, Python 3, bez dodatnih paketa."""
import argparse
import ctypes
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
KINDS = {'PushEvent': 'push', 'WatchEvent': 'star', 'ForkEvent': 'fork'}
LOG = logging.getLogger('git_sound')


def load_config():
    defaults = json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8-sig'))
    local = ROOT / 'config.json'
    if local.exists():
        overrides = json.loads(local.read_text(encoding='utf-8-sig'))
        defaults['sounds'].update(overrides.pop('sounds', {}))
        defaults.update(overrides)
    return defaults


def resolve_sound(config, kind):
    """Newest custom kind_name.wav/mp3 wins; bundled tones are the fallback."""
    if kind not in ('push', 'star', 'fork'):
        raise ValueError('Nepoznat dogadjaj: ' + kind)
    selected = config.get('sounds', {}).get(kind, 'auto')
    if selected and selected != 'auto':
        filename = (ROOT / selected).resolve()
        if not filename.is_file():
            raise ValueError('Zvuk ne postoji: ' + str(filename))
        return filename
    directory = ROOT / config.get('sounds_directory', 'sounds')
    candidates = [p for p in directory.iterdir() if p.is_file()
                  and p.suffix.lower() in ('.wav', '.mp3')
                  and p.stem.lower().startswith(kind + '_')
                  and len(p.stem) > len(kind) + 1] if directory.exists() else []
    if candidates:
        return max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name.casefold()))
    fallback = ROOT / 'sounds' / 'defaults' / (kind + '.wav')
    if not fallback.is_file():
        raise ValueError('Nema zvuka za ' + kind + '. Pokreni Install.bat ili dodaj ' + kind + '_ime.wav u sounds.')
    return fallback


class GitHub:
    def __init__(self):
        self.etags = {}
        self.due = {}
        self.blocked_until = 0
        cooldown = ROOT / 'api_cooldown.json'
        if cooldown.exists():
            try:
                self.blocked_until = float(json.loads(cooldown.read_text())['until'])
            except (ValueError, KeyError):
                pass

    def get(self, path, conditional=False):
        if time.time() < max(self.blocked_until, self.due.get(path, 0)):
            return None
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Git-Sound'}
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if conditional and path in self.etags:
            headers['If-None-Match'] = self.etags[path]
        request = urllib.request.Request('https://api.github.com' + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                if conditional:
                    self.etags[path] = response.headers.get('ETag', '')
                    self.due[path] = time.time() + max(60, int(response.headers.get('X-Poll-Interval', 60)))
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                self.due[path] = time.time() + max(60, int(exc.headers.get('X-Poll-Interval', 60)))
                return None
            if exc.code in (403, 429):
                delay = max(60, int(exc.headers.get('Retry-After', 60)))
                if exc.headers.get('X-RateLimit-Remaining') == '0':
                    delay = max(delay, int(exc.headers.get('X-RateLimit-Reset', 0)) - time.time() + 5)
                self.due[path] = time.time() + delay
                self.blocked_until = time.time() + delay
                (ROOT / 'api_cooldown.json').write_text(json.dumps({'until': self.blocked_until}))
                LOG.warning('GitHub ogranicenje: pauza do %s.', time.strftime('%H:%M:%S', time.localtime(self.blocked_until)))
            raise


def play(config, kind, stop=None):
    filename = resolve_sound(config, kind)
    LOG.info('Zvuk %s: %s', kind, filename.name)
    # Windows MCI podrzava WAV i MP3; duljinu ogranicavamo i zasebnim satom.
    mci = ctypes.windll.winmm.mciSendStringW
    def command(value):
        error = mci(value, None, 0, None)
        if error:
            description = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(error, description, len(description))
            raise RuntimeError(f'Windows audio greska {error}: {description.value} ({filename.name})')
    try:
        with filename.open('rb') as source:
            header = source.read(12)
        # Renamed MP3 files sometimes retain a .wav suffix. Inspect the contents.
        media_type = 'waveaudio' if header[:4] == b'RIFF' and header[8:12] == b'WAVE' else 'mpegvideo'
        command(f'open "{filename}" type {media_type} alias gitsound')
        command('set gitsound time format milliseconds')
        duration = min(15.0, max(0.1, float(config.get('duration_seconds', 15))))
        length = ctypes.create_unicode_buffer(64)
        error = mci('status gitsound length', length, len(length), None)
        if not error and length.value.isdigit():
            duration = min(duration, int(length.value) / 1000)
        command(f'play gitsound from 0 to {int(duration * 1000)}')
        if stop:
            stop.wait(duration)
        else:
            time.sleep(duration)
    finally:
        mci('close gitsound', None, 0, None)


def save_state(state):
    temporary = ROOT / 'state.tmp'
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(ROOT / 'state.json')


def consume_events(state, repo, events):
    """Prvi dohvat je pocetno stanje; kasnije pustamo samo nove ID-jeve."""
    known = state.get(repo)
    ids = [str(event['id']) for event in events]
    fresh = [] if known is None else [e for e in reversed(events) if str(e['id']) not in set(known)]
    state[repo] = list(dict.fromkeys(ids + (known or [])))[:1000]
    return [e for e in fresh if e.get('type') in KINDS]


def repositories(api, config):
    result = set(config.get('repositories', []))
    for owner in config.get('owners', []):
        page = 1
        while True:
            data = api.get('/users/' + urllib.parse.quote(owner, safe='') + f'/repos?type=owner&per_page=100&page={page}')
            if data is None:
                raise RuntimeError('GitHub trenutno ogranicava dohvat repozitorija.')
            result.update(item['full_name'] for item in data)
            if len(data) < 100:
                break
            page += 1
    for repo in result:
        if len(repo.split('/')) != 2 or any(not part for part in repo.split('/')):
            raise ValueError('Repozitorij mora biti vlasnik/repozitorij: ' + repo)
    return sorted(result)


def run(config, once=False):
    state_path = ROOT / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    api = GitHub()
    sounds = queue.Queue(maxsize=30)
    stop = threading.Event()
    def worker():
        while not stop.is_set():
            try:
                kind = sounds.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                play(load_config(), kind, stop)
            except Exception as exc:
                LOG.error('Ne mogu pustiti zvuk: %s', exc)
            finally:
                sounds.task_done()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    repos = []
    refresh_at = 0
    try:
        while True:
            if time.time() >= refresh_at:
                try:
                    repos = repositories(api, config)
                    LOG.info('Pratim %s repozitorija.', len(repos))
                    refresh_at = time.time() + 900
                except Exception as exc:
                    LOG.warning('Dohvat popisa nije uspio: %s', exc)
                    refresh_at = time.time() + 60
            for repo in repos:
                try:
                    events = api.get('/repos/' + urllib.parse.quote(repo, safe='/') + '/events?per_page=100', conditional=True)
                    if events is None:
                        continue
                    fresh = consume_events(state, repo, events)
                    save_state(state)
                    for event in fresh:
                        kind = KINDS[event['type']]
                        LOG.info('%s | %s | %s', kind, repo, event.get('actor', {}).get('login', '?'))
                        try:
                            sounds.put_nowait(kind)
                        except queue.Full:
                            LOG.warning('Red zvukova je pun; preskacem zvuk.')
                except Exception as exc:
                    LOG.warning('%s: %s', repo, exc)
            if once:
                sounds.join()
                break
            interval = max(60, int(config.get('poll_seconds', 60)))
            if not os.environ.get('GITHUB_TOKEN'):
                # Ostavlja prostor za osvjezavanje popisa uz anonimni limit 60/h.
                interval = max(interval, len(repos) * 90)
            time.sleep(interval)
    finally:
        stop.set()
        thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', choices=['push', 'star', 'fork'])
    parser.add_argument('--once', action='store_true', help='Jedan krug provjere')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.StreamHandler(), logging.FileHandler(ROOT / 'git_sound.log', encoding='utf-8')])
    config = load_config()
    if args.test:
        play(config, args.test)
        return
    # Sprjecava dvije instance da istodobno pustaju i biljeze iste dogadjaje.
    mutex_api = ctypes.windll.kernel32.CreateMutexW
    mutex_api.restype = ctypes.c_void_p
    instance_id = hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:16]
    handle = mutex_api(None, True, 'Local\\GitSound-' + instance_id)
    if ctypes.windll.kernel32.GetLastError() == 183:
        raise SystemExit('Git Sound je vec pokrenut.')
    try:
        if args.test:
            play(config, args.test)
        else:
            if config.get('mode') == 'webhook' and not args.once:
                from webhook_app import run as run_webhooks
                while True:
                    try:
                        run_webhooks(config)
                    except Exception:
                        LOG.exception('Webhook veza je prekinuta. Novi pokusaj za 60 sekundi.')
                        time.sleep(60)
            else:
                if not config.get('owners'):
                    from webhook_app import API
                    config['owners'] = [API().call('/user')['login']]
                run(config, args.once)
    except KeyboardInterrupt:
        LOG.info('Zaustavljeno.')
    except Exception:
        LOG.exception('Git Sound je zaustavljen zbog greske.')
        raise
    finally:
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close(handle)


if __name__ == '__main__':
    main()
