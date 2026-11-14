# v0.4.11

## Unreleased

- Fixed installed CLI and GUI imports and fork release checks. Pinned the GUI extra and removed unused remote API key loading.
- Added shared rate-limit backoff, a resumable queue pause, and a failed-track report.
- Improved GUI shutdown and Windows filename handling. Completed media is now published atomically.
- Added optional OS keyring storage with migration, dependency checks, and a Windows setup guide.
- Updated fork metadata and removed PyPI publishing and docs deployment from release CI.


- Fixes regarding empty metadata tags (also fixes #1).
- CLI downloader extended to handle playlists and mixes.
- `Download.track()` now handles logger functions.
- GUI build for macOS and asset upload.

# v0.4.9

- Fixed: Exception on missing file read (config, token) instead of creation.

# v0.4.8

- Fixed: GUI dependencies are treated as extra now (pip).

# v0.4.7

- Fixed: GUI dependencies are treated as extra now (pip).

# v0.4.6

- GUI dependencies are treated as extra now (pip).

# v0.4.5

- Fixed "Mix" download.
- Fixed relative imports.
- Fixed PyPi build.
- Fixed crash on lyrics error.

# v0.4.2

- Added more basic features.

# v0.4.1

- Initial featured running version.
