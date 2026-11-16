import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

import git_sound
import webhook_app


class SoundSelectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.patch = patch.object(git_sound, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.root / 'sounds' / 'defaults').mkdir(parents=True)
        for kind in ('push', 'star', 'fork'):
            (self.root / 'sounds' / 'defaults' / (kind + '.wav')).write_bytes(b'default')

    def song(self, name, timestamp=100):
        path = self.root / 'sounds' / name
        path.write_bytes(b'custom')
        os.utime(path, ns=(timestamp, timestamp))
        return path

    def test_newest_custom_file_wins_across_wav_and_mp3(self):
        self.song('push_old.wav', 100)
        expected = self.song('push_new.mp3', 200)
        self.song('star_newest.wav', 300)
        self.assertEqual(git_sound.resolve_sound({}, 'push'), expected)

    def test_rename_is_seen_on_next_event(self):
        old = self.song('push_first.wav')
        self.assertEqual(git_sound.resolve_sound({}, 'push'), old)
        new = old.rename(old.with_name('push_second.wav'))
        self.assertEqual(git_sound.resolve_sound({}, 'push'), new)

    def test_case_unicode_and_spaces(self):
        expected = self.song('PUSH_Čudna pjesma.WAV')
        self.assertEqual(git_sound.resolve_sound({}, 'push'), expected)

    def test_fallback_ignores_wrong_prefix_empty_name_and_other_extensions(self):
        for name in ('push.wav', 'push_.wav', 'push_fake.exe', 'notpush_song.mp3'):
            self.song(name)
        self.assertEqual(git_sound.resolve_sound({}, 'push'), self.root / 'sounds/defaults/push.wav')

    def test_ties_are_stable(self):
        self.song('push_a.wav')
        expected = self.song('push_b.wav')
        self.assertEqual(git_sound.resolve_sound({}, 'push'), expected)

    def test_explicit_path_overrides_automatic_selection(self):
        expected = self.song('selected.mp3')
        self.song('push_other.wav', 999)
        self.assertEqual(git_sound.resolve_sound({'sounds': {'push': 'sounds/selected.mp3'}}, 'push'), expected)

    def test_missing_explicit_path_reports_error(self):
        with self.assertRaisesRegex(ValueError, 'Zvuk ne postoji'):
            git_sound.resolve_sound({'sounds': {'push': 'missing.wav'}}, 'push')

    def test_clean_clone_loads_template_without_local_account_config(self):
        (self.root / 'config.example.json').write_text(json.dumps({'owners': [], 'sounds': {'push': 'auto'}}))
        self.assertEqual(git_sound.load_config()['owners'], [])

    def test_partial_local_config_preserves_other_defaults(self):
        (self.root / 'config.example.json').write_text(json.dumps({'owners': [], 'sounds': {'push': 'auto', 'star': 'auto'}}))
        (self.root / 'config.json').write_text(json.dumps({'sounds': {'push': 'sounds/custom.wav'}}))
        self.assertEqual(git_sound.load_config()['sounds'], {'push': 'sounds/custom.wav', 'star': 'auto'})


class AccountTests(unittest.TestCase):
    def test_automatic_account_is_not_hardcoded(self):
        self.assertEqual(webhook_app.account_owners({'owners': []}, 'AnyUser'), ['AnyUser'])

    def test_another_accounts_config_is_rejected(self):
        with self.assertRaises(ValueError):
            webhook_app.account_owners({'owners': ['SomeoneElse']}, 'AnyUser')


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.sounds = queue.Queue(maxsize=1)
        self.receiver = webhook_app.Receiver('test-secret', ['AnyUser'], self.sounds,
                                             Path(self.folder.name) / 'deliveries.db')
        self.addCleanup(self.receiver.db.close)

    def event(self, event='star', delivery='id-1', action='created', owner='AnyUser', valid=True):
        body = json.dumps({'action': action, 'repository': {'full_name': owner + '/private-repo', 'private': True}}).encode()
        signature = 'sha256=' + hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
        headers = {'X-GitHub-Event': event, 'X-GitHub-Delivery': delivery,
                   'X-Hub-Signature-256': signature if valid else 'sha256=invalid'}
        return self.receiver.accept(headers, body)

    def test_signed_private_event_and_duplicate(self):
        self.assertEqual(self.event(), 200)
        self.assertEqual(self.sounds.get_nowait(), 'star')
        self.assertEqual(self.event(), 200)
        self.assertTrue(self.sounds.empty())

    def test_unsigned_or_wrong_owner_event_is_rejected(self):
        self.assertEqual(self.event(valid=False), 401)
        self.assertEqual(self.event(owner='OtherUser'), 403)
        self.assertTrue(self.sounds.empty())

    def test_unstar_is_ignored(self):
        self.assertEqual(self.event(action='deleted'), 200)
        self.assertTrue(self.sounds.empty())

    def test_full_queue_can_retry_after_drain(self):
        self.assertEqual(self.event('push', 'id-1'), 200)
        self.assertEqual(self.event('fork', 'id-2'), 503)
        self.assertEqual(self.sounds.get_nowait(), 'push')
        self.assertEqual(self.event('fork', 'id-2'), 200)
        self.assertEqual(self.sounds.get_nowait(), 'fork')


if __name__ == '__main__':
    unittest.main()
