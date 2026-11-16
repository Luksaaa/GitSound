# Git Sound

Play a short sound on your Windows PC when someone pushes, stars, or forks one of
your GitHub repositories. Public and private repositories are supported.

**Windows 10/11 · Python 3.10+ · Python standard library only · MIT license**

## Quick start

1. Clone or download this repository.
2. Install Python 3.10+ and Git for Windows with Git Credential Manager. Make sure
   `python` and `git` work in a new terminal.
3. Authenticate Git for `github.com` with Git Credential Manager, or provide a
   `GITHUB_TOKEN` environment variable. Never put a token in a project file.
4. Run `Install.bat`. It creates your local configuration, checks your GitHub login,
   and downloads Cloudflare's `cloudflared` executable with SHA256 verification.
5. Run `start_background.bat` for background mode, or `start.bat` for a console window.

The account is detected from your GitHub login. Git Sound automatically creates
webhooks for **repositories owned by that account** where you have admin access,
including private repositories. New repositories are discovered every 15 minutes.
It updates only the webhook IDs recorded in its local `webhook_registry.json`.
Do not copy that file from someone else's installation.

For a fine-grained personal access token, choose your account as resource owner,
select **All repositories**, and grant repository **Webhooks: Read and write**
plus **Metadata: Read**. Access restrictions, expired tokens, and organization
policies may prevent setup. Organization repositories and other users'
repositories are outside the automatic account-wide setup.

## Pick your own music

Put your WAV or MP3 files directly in `sounds/`:

| Event | Example filenames |
| --- | --- |
| Push | `push_travis.wav`, `push_my song.mp3` |
| New star | `star_celebration.wav` |
| Fork | `fork_ding.mp3` |

The name after the underscore is yours to choose. Prefixes and extensions are
case insensitive. Each new event selects the **most recently modified** matching
file; a file-name tie breaker makes the result deterministic. Keep one custom
file per event if you prefer a fixed selection.

You can rename or replace songs while the app runs. No configuration change or
restart is needed. If no matching custom file exists, a bundled generated melody
is used. `push.wav` by itself does not match `push_`; use `push_name.wav`.
The normal setting in `config.json` is `"sounds": {"push": "auto", ...}`.
An explicit file path is also supported as an advanced override.

Each sound is limited to **15 seconds**; shorter files finish sooner. Changing a
file's extension does not convert its audio. Standard WAV and MP3 files work with
the Windows media system; codec support depends on Windows.

Your custom music is ignored by Git. The three bundled melodies were generated
for this project and are covered by the MIT license.

## Controls

| File / command | Purpose |
| --- | --- |
| `Install.bat` | First-run setup; existing local config is preserved |
| `start_background.bat` | Start in the background |
| `start.bat` | Start with visible logs |
| `test_push.bat` | Play the selected push sound |
| `test_star.bat` | Play the selected star sound |
| `python git_sound.py --test fork` | Play the selected fork sound |
| `stop.bat` | Stop the local app and its tunnel |

`git_sound.log` records events, selected sound names, and errors.
`webhook_status.json` lists setup successes and failures. These local files may
contain private repository names and are excluded from Git.

## How it works

GitHub sends a signed webhook to a public HTTPS Cloudflare Quick Tunnel. That
tunnel forwards only to the local receiver at `127.0.0.1:8765`. The receiver checks
the HMAC-SHA256 signature and account owner, rejects untrusted requests, and queues
the corresponding sound. Delivery IDs are stored for 30 days to avoid duplicates.
Removing a star does not play a sound; only a newly created star does.

The tunnel address changes after restarting. Git Sound automatically updates its
webhooks to the new address. No router port forwarding is needed. Cloudflare
transports webhook payloads, including metadata for private repository events.

### Practical limits

- Your PC must be awake, online, and running Git Sound. There is no automatic
  Windows startup entry.
- Quick Tunnels are intended for development and have no availability guarantee.
  Tunnel failures are retried after 60 seconds. A named Cloudflare tunnel is a
  future option for a stable deployment, not configured by this project.
- Events during downtime may be missed. GitHub does not automatically redeliver
  every failed webhook. Once online, use **Settings > Webhooks > Recent Deliveries
  > Redeliver** if needed.
- Sounds play sequentially. Up to 30 sounds can wait; a full queue returns HTTP
  503. Accepted deliveries are recorded before playback, so a crash or audio
  failure can cause a sound to be skipped.
- Run one installation per account unless you understand webhook duplication.
  Local instance locking is scoped to the installation directory.
- Optional polling mode (`"mode": "poll"`) uses the Events API with substantial
  latency and API limits; its automatic owner lookup lists public repositories.
  Webhook mode is the supported path for private repositories and fast alerts.

## Local configuration and removal

`config.example.json` is the shared template. `Install.bat` copies it to the
ignored `config.json` on first run. With `"owners": []`, the signed-in user is
selected automatically. A nonempty owners list must match that user.

Sound settings reload on each event. Restart after changing the port or account.
Keep `.webhook-secret` and `webhook_registry.json` local and intact so the same
installation can authenticate deliveries and update its existing hooks.

Stopping the app does **not** remove webhooks on GitHub. To uninstall completely,
stop it and remove its webhook entries from each repository's Settings > Webhooks.
The recorded IDs in `webhook_registry.json` identify the entries it manages.

## Development

```powershell
python -m unittest discover -s tests -v
```

Tests run offline without changing GitHub settings or playing audio.

See [INSTRUCTIONS.hr.md](INSTRUCTIONS.hr.md) for Croatian instructions and [LICENSE](LICENSE) for reuse.

References: [GitHub webhooks](https://docs.github.com/en/rest/repos/webhooks),
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
