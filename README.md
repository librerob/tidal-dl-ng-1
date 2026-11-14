# 🔰 TIDAL Downloader Next Generation! (tidal-dl-ng)

[![Release](https://img.shields.io/github/v/release/librerob/tidal-dl-ng-1?include_prereleases)](https://github.com/librerob/tidal-dl-ng-1/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/librerob/tidal-dl-ng-1/windows-portable.yml)](https://github.com/librerob/tidal-dl-ng-1/actions/workflows/windows-portable.yml)
[![Commit activity](https://img.shields.io/github/commit-activity/m/librerob/tidal-dl-ng-1)](https://img.shields.io/github/commit-activity/m/librerob/tidal-dl-ng-1)
[![License](https://img.shields.io/github/license/librerob/tidal-dl-ng-1)](https://img.shields.io/github/license/librerob/tidal-dl-ng-1)

This tool allows to download songs and videos from TIDAL. Multithreaded and multi-chunked downloads are supported.

**A paid TIDAL plan is required!** Audio quality varies up to HiRes Lossless / TIDAL MAX 24-bit, 192 kHz depending on the song available. You can use the command line or GUI version of this tool.

![App Image](assets/app.png)

## Portable Windows app

[Download the Windows x64 preview ZIP](https://github.com/librerob/tidal-dl-ng-1/releases/download/0.24.6-preview.1/tidal-dl-ng-windows-x64.zip) and extract the entire archive. Double-click `TIDAL Downloader.exe` and keep the accompanying files alongside it. Python and Qt are included. For FLAC extraction or video conversion, install FFmpeg separately and set `path_binary_ffmpeg` in Settings.

The [preview release page](https://github.com/librerob/tidal-dl-ng-1/releases/tag/0.24.6-preview.1) has the SHA-256 checksum and release notes.

## Windows quickstart from source

Install Python 3.12, then run these commands from the checkout in PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install ".[gui]"
winget install Gyan.FFmpeg
tdng
```

After installing FFmpeg, set `path_binary_ffmpeg` in Settings to the full path to `ffmpeg.exe`.

## Troubleshooting

- **TIDAL returns HTTP 429.** The downloader waits before retrying. If the queue pauses, give TIDAL time to recover, then resume it in the GUI or rerun the same CLI command with `skip_existing` enabled.
- **Some tracks failed.** Look for `failed_tracks.json` in the configured download folder. It records each attempted failure with its track ID, title, artist, playlist, and reason. Run `tdn retry-failed` to retry eligible standalone tracks. Reopen the original playlist to retry playlist failures in their original folders.
- **Turn off startup update checks.** Clear `check_for_updates` in GUI settings or run `tdn cfg check_for_updates false`.
- **Use the system keyring.** Install with `pip install ".[gui,keyring]"` and run `tdn cfg use_keyring true`. On the next launch, an existing token moves to the keyring when available.

## Install or upgrade the fork from source

Use Python 3.12 and install from this repository's checkout. Run `git pull` first when upgrading an existing checkout. In your active virtual environment, run `python -m pip install --upgrade .` for the CLI or `python -m pip install --upgrade ".[gui]"` for the GUI and CLI.

## ⌨️ Usage

You can use the command line (CLI) version to download media by URL:

```bash
tidal-dl-ng dl https://tidal.com/browse/track/46755209
# OR
tdn dl https://tidal.com/browse/track/46755209
```

Or by your favorites collections:

```bash
tidal-dl-ng dl_fav tracks
tidal-dl-ng dl_fav artists
tidal-dl-ng dl_fav albums
tidal-dl-ng dl_fav videos
```

You can also use the GUI:

```bash
tidal-dl-ng-gui
# OR
tdng
# OR
tidal-dl-ng gui
```

Run `tdn --help` for all commands. Use `tdn verify-files` to list missing files or changes in size or timestamp for files previously recorded by a playlist checkpoint.

### Playlist recovery

Reopen the same ordered playlist with the same output folder, filename template, and quality. The local SQLite checkpoint preserves completed files that still exist and are non-empty, including retagged files. Missing and empty files can be downloaded again. Generated playlist files follow the source playlist order.

If the checkpoint is unreadable, the app warns you, leaves the database in place, and continues with the normal download settings, including `skip_existing`.

## 🧁 Features

- Download tracks, videos, albums, playlists, your favorites etc.
- Multithreaded and multi-chunked downloads
- Metadata for songs
- Adjustable audio and video download quality.
- FLAC extraction from MP4 containers
- Lyrics and album art / cover download
- Creates playlist files
- Can symlink tracks instead of having several copies, if added to different playlist

## ▶️ Getting started with development

### 🚰 Install dependencies

Clone this repository and install the dependencies:

```bash
poetry install --all-extras --with dev,docs
```

The main entry points are:

```bash
tidal_dl_ng/cli.py
tidal_dl_ng/gui.py
```

### 📺 GUI Builder

The GUI is build with `PySide6` using the [Qt Designer](https://doc.qt.io/qt-6/qtdesigner-manual.html):

```bash
PYSIDE_DESIGNER_PLUGINS=tidal_dl_ng/ui pyside6-designer
```

After all changes are saved you need to translate the Qt Designer `*.ui` file into Python code, for instance:

```
pyside6-uic tidal_dl_ng/ui/main.ui -o tidal_dl_ng/ui/main.py
```

This needs to be done for each created / modified `*.ui` file accordingly.

### 🏗 Build the project

To build the project use this command:

```bash
make install
# OR
make gui-macos
```

See the `Makefile` for all available build commands.

The [portable Windows workflow](https://github.com/librerob/tidal-dl-ng-1/actions/workflows/windows-portable.yml) tests a clean installation, builds the ZIP, and launches the extracted executable before uploading the artifact.

## Troubleshooting the packaged app

### Windows flags the executable

The preview executable is unsigned. Check the ZIP against the SHA-256 checksum on the release page and review any warning from your security software before running it.

### I get an error when `extract_flac` is enabled.

Set `path_binary_ffmpeg` to the full path to the FFmpeg executable and try again.

## ‼️ Disclaimer

- For educational purposes only. I am not liable and responsible for any damage that happens.
- You should not use this method to distribute or pirate music.
- It may be illegal to use this app in your country.

## 🫂 Contributors

Thanks to all, who have contributed to this project!

This project is based on:

- https://fpgmaas.github.io/cookiecutter-poetry/
