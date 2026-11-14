# 🔰 TIDAL Downloader Next Generation! (tidal-dl-ng)

[![Release](https://img.shields.io/github/v/release/librerob/tidal-dl-ng-1)](https://img.shields.io/github/v/release/librerob/tidal-dl-ng-1)
[![Build status](https://img.shields.io/github/actions/workflow/status/librerob/tidal-dl-ng-1/on-release-master.yml)](https://github.com/librerob/tidal-dl-ng-1/actions/workflows/on-release-master.yml)
[![Commit activity](https://img.shields.io/github/commit-activity/m/librerob/tidal-dl-ng-1)](https://img.shields.io/github/commit-activity/m/librerob/tidal-dl-ng-1)
[![License](https://img.shields.io/github/license/librerob/tidal-dl-ng-1)](https://img.shields.io/github/license/librerob/tidal-dl-ng-1)

This tool allows to download songs and videos from TIDAL. Multithreaded and multi-chunked downloads are supported.


**A paid TIDAL plan is required!** Audio quality varies up to HiRes Lossless / TIDAL MAX 24-bit, 192 kHz depending on the song available. You can use the command line or GUI version of this tool.

![App Image](assets/app.png)

```bash
$ tidal-dl-ng --help

 Usage: tidal-dl-ng [OPTIONS] COMMAND [ARGS]...

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --version  -v                                                                │
│ --help     -h        Show this message and exit.                             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ cfg    Print or set an option. If no arguments are given, all options will   │
│        be listed. If only one argument is given, the value will be printed   │
│        for this option. To set a value for an option simply pass the value   │
│        as the second argument                                                │
│ dl                                                                           │
│ dl_fav Download from a favorites collection.                                 │
│ gui                                                                          │
│ login                                                                        │
│ logout                                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```




## Portable Windows app

Download the Windows portable ZIP from the fork's GitHub Actions artifacts or Releases, extract the entire ZIP, and open `TIDAL Downloader.exe`. Keep the accompanying DLLs and Qt files alongside the executable. The app includes Python and Qt. FFmpeg is optional and can be configured in Settings for media conversion.

## Windows quickstart from source

Install Python 3.12, then run these commands from the checkout in PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install ".[gui]"
winget install Gyan.FFmpeg
tdng
```

If FFmpeg was just installed, open a new terminal and activate the venv again so Windows picks up the updated PATH.

## Troubleshooting

- **TIDAL returns HTTP 429.** The downloader waits before retrying. If the queue pauses, give TIDAL time to recover, then resume it in the GUI or rerun the same CLI command with `skip_existing` enabled.
- **Some tracks failed.** Look for `failed_tracks.json` in the configured download folder. It records each attempted failure with its track ID, title, artist, playlist, and reason. Use the IDs to re-queue the failed tracks after resolving the error.
- **Turn off startup update checks.** Clear `check_for_updates` in GUI settings or run `tdn cfg check_for_updates false`.
- **Use the system keyring.** Install with `pip install ".[gui,keyring]"` and run `tdn cfg use_keyring true`. On the next launch, an existing token moves to the keyring when available.


## 💻 Installation / Upgrade

**Requirements**: Python == 3.12 (other versions might work but are not tested!)

```bash
pip install --upgrade tidal-dl-ng
# If you like to have the GUI as well use this command instead
pip install --upgrade tidal-dl-ng[gui]
```

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

If you like to have the GUI version only as a binary, have a look at the
[release page](https://github.com/librerob/tidal-dl-ng-1/releases) and download the correct version for your platform.

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
tidal_ng_dl/cli.py
tidal_ng_dl/gui.py
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

The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.

To finalize the set-up for publishing to PyPi or Artifactory, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/publishing/#set-up-for-pypi).
For activating the automatic documentation with MkDocs, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/mkdocs/#enabling-the-documentation-on-github).
To enable the code coverage reports, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/codecov/).

## ❓ FAQ

### macOS Error Message: File/App is damaged and cannot be opened. You should move it to Trash..

If you download an (unsigned) app from any source other than those that Apple seems suited, the application gets an extended attribute "com.apple.Quarantine". This triggers the message: "<application> is damaged and can't be opened. You should move it to the Bin."

Remove the attribute and you can launch the application. [Source 1](https://discussions.apple.com/thread/253714860?sortBy=rank) [Source 2](https://www.reddit.com/r/macsysadmin/comments/13vu7f3/app_is_damaged_and_cant_be_opened_error_on_ventura/)

```
$ sudo xattr -dr com.apple.quarantine /Applications/TIDAL-Downloader-NG.app/
```

Why is this app unsigned? Only developer enrolled in the paid Apple developer program are allowed to sign (legal) apps. Without this subscription app signing is not possible.

Gatekeeper really annoys you, and you like to disable it completely? Follow this [link](https://iboysoft.com/tips/how-to-disable-gatekeeper-macos-sequoia.html)

### My (Windows) antivirus app XYZ says the GUI version of this app is harmful.

Short answer: It is a lie. Get rid of your antivirus app.

Verify the archive checksum and review your security software's report before running the app.

### I get an error when `extract_flac` is enabled.

Your `path_binary_ffmpeg` is probably wrong. Please read over and over again the help of this particular option until you get it right what path to put for `path_binary_ffmpeg`.

## ‼️ Disclaimer

- For educational purposes only. I am not liable and responsible for any damage that happens.
- You should not use this method to distribute or pirate music.
- It may be illegal to use this app in your country.

## 🫂 Contributors

Thanks to all, who have contributed to this project!

This project is based on:

- https://fpgmaas.github.io/cookiecutter-poetry/
