# Custom sounds

Drop your own WAV or MP3 files here:

- `push_song.wav` or `push_song.mp3`
- `star_song.wav` or `star_song.mp3`
- `fork_song.wav` or `fork_song.mp3`

Replace `song` with any name, including spaces or Unicode characters. Prefixes and
extensions are case insensitive. Only files directly in this directory are searched.
Leave the corresponding `sounds` value in `config.json` set to `"auto"`.

The most recently modified matching file is selected for each event. Ties are
resolved by file name. Remove the old file when you only want one choice.
With no matching custom file, the generated tone in `defaults/` is used.
Names such as `push.wav` do not match the `push_` custom prefix.

Changes apply to the next sound without restarting. Each clip plays for up to
15 seconds. Renaming `.mp3` to `.wav` does not convert the audio format.
Your music is excluded from Git by default; the bundled tones are generated
specifically for this project and are covered by the project license.
