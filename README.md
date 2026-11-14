<div align="center">
  <img src="assets/tdn-readme-hero.svg" width="100%" alt="TIDAL Downloader NG">

  <p>Download TIDAL tracks, albums, playlists, and videos from the desktop app or CLI.</p>

  <p>
    <a href="https://github.com/librerob/tidal-dl-ng-1/releases/download/0.24.6-preview.1/tidal-dl-ng-windows-x64.zip"><img src="https://img.shields.io/badge/Download-Windows_x64-63EAD8?style=for-the-badge&amp;labelColor=141A32" alt="Download for Windows x64"></a>
    <a href="https://github.com/librerob/tidal-dl-ng-1/releases/tag/0.24.6-preview.1"><img src="https://img.shields.io/badge/Release-0.24.6_preview.1-B2A1FF?style=for-the-badge&amp;labelColor=141A32" alt="Release 0.24.6 preview 1"></a>
  </p>

  <p><a href="#features">Features</a> · <a href="#install-from-source">Source install</a> · <a href="#recovery-and-settings">Recovery and settings</a></p>

  <img src="assets/app.png" width="860" alt="TIDAL Downloader NG desktop app">
</div>

A paid TIDAL plan is required. Available audio quality depends on the track and your account.

## Windows download

1. [Download the Windows x64 preview ZIP](https://github.com/librerob/tidal-dl-ng-1/releases/download/0.24.6-preview.1/tidal-dl-ng-windows-x64.zip).
2. Extract the entire ZIP and open `TIDAL Downloader.exe`.

Python and Qt are bundled. Keep the extracted files together. The preview is unsigned, and the SHA-256 checksum is on the [release page](https://github.com/librerob/tidal-dl-ng-1/releases/tag/0.24.6-preview.1).

FFmpeg is optional. Install it separately for video conversion or FLAC extraction, then set `path_binary_ffmpeg` to the full path to `ffmpeg.exe` in Settings.

## Features

| Feature | What you can do |
| --- | --- |
| **Media and quality** | Download tracks, albums, playlists, mixes, videos, and favorites. Choose the audio or video quality. |
| **Library organization** | Save tags, lyrics, and cover art where available. Choose filename templates, generate M3U8 playlists in source order, and optionally link shared tracks across playlists. |
| **Queue recovery** | Wait and retry after a rate limit, or resume the same playlist from a local checkpoint. Existing non-empty files, including retagged files, are preserved. |
| **File checks** | Report failures, retry eligible standalone tracks, and check previously recorded files for changes. |
| **Login storage** | Save credentials in the system keyring when enabled. |

## Install from source

Clone this repository, then run the following in PowerShell with Python 3.12 installed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install ".[gui]"
tdng
```

For the CLI alone, install with `python -m pip install .`. To upgrade a source install, run `git pull` and repeat the install command in the same virtual environment.

### CLI examples

```powershell
tdn dl https://tidal.com/browse/track/46755209
tdn dl_fav tracks
tdn retry-failed
tdn verify-files
```

Run `tdn --help` for all commands.

## Recovery and settings

- **Rate limit (HTTP 429).** The app waits before retrying. If the queue pauses, resume in the GUI after the cooldown or rerun the CLI command with `skip_existing` enabled.
- **Playlist interrupted.** Reopen the same ordered playlist with the same output folder, filename template, and quality. The checkpoint preserves completed non-empty files and lets missing or empty files be downloaded again. If the database is unreadable, the app leaves it in place and continues with the normal download settings.
- **Failed or changed files.** Look for `failed_tracks.json` in the download folder. Use `tdn retry-failed` for eligible standalone tracks and reopen the original playlist for playlist failures. Use `tdn verify-files` to report missing files or changes in size or modification time.
- **Login storage.** Enable `use_keyring` with `tdn cfg use_keyring true`. For source installs, install the optional dependency with `python -m pip install ".[gui,keyring]"`. The app migrates an existing saved login on the next launch when the keyring is available.
- **Update checks.** Disable startup checks in GUI Settings or with `tdn cfg check_for_updates false`.

## Development

Install development dependencies with `poetry install --all-extras --with dev,docs`. The entry points are `tidal_dl_ng/cli.py` and `tidal_dl_ng/gui.py`. See the [Makefile](Makefile) for build targets and the [Windows workflow](.github/workflows/windows-portable.yml) for the clean-install and portable launch checks.

Licensed under the [GNU AGPL v3](LICENSE).
