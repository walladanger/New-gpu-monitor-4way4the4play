# Install GPU Live Graphs 0.5.0

## Download

Open the [0.5.0 preview release](https://github.com/walladanger/New-gpu-monitor-4way4the4play/releases/tag/v0.5.0).

| File | Use |
| --- | --- |
| `GPU-Live-Graphs-0.5.0-Setup.exe` | Per-user installation, shortcuts, and uninstall support |
| `GPU-Live-Graphs-0.5.0-Windows-x64.zip` | Portable application folder; extract everything before launching |
| `SHA256SUMS-Windows.txt` | SHA-256 checksums for both packages |

These packages include Python, Tk, and Pillow. An NVIDIA driver providing `nvidia-smi` is required; Python, a CUDA Toolkit, and an API key are not. The build is currently unsigned.

## Install and update

1. Close existing GPU Live Graphs windows.
2. Run Setup. It installs under `%LOCALAPPDATA%\Programs\GPU Live Graphs` for the current account.
3. Use the Start menu shortcut. A desktop shortcut is optional.

Updates keep the same application identity and user-data location. The installer can request closure of a running copy whose files need updating. History and preferences remain outside the installed program files.

For the portable ZIP, extract the complete `GPU-Live-Graphs` folder and run `GPU-Live-Graphs.exe`. Do not move only the EXE away from its `_internal` directory.

## User data and uninstall

Open `%LOCALAPPDATA%\GPU Live Graphs` in File Explorer:

- `history.sqlite3`: up to 24 hours of saved query records; database cap 128 MB.
- `preferences.json`: versioned appearance, selection, and window state.
- `exports/` and `captures/`: user-created CSV/PDF/PNG files.
- `logs/`: Python errors and native-fault reports.

Uninstall through **Windows Settings → Apps → Installed apps → GPU Live Graphs**. The app files and shortcuts are removed; user data is retained.

To reset preferences without losing a backup, close the app and rename `preferences.json`, then launch again. Do not edit or copy the database while the app is writing to it.

## Verify a download

```powershell
Get-FileHash .\GPU-Live-Graphs-0.5.0-Setup.exe -Algorithm SHA256
```

Compare the value with the release's checksum file.

## Build locally

On Windows with Python 3.11 and Inno Setup 6 or later:

```powershell
python -m pip install -r requirements-build.txt
./tools/build_windows.ps1
```

The workflow builds with Python 3.11, even though source tests also cover 3.14. Build tooling is pinned separately from runtime requirements.

## Package verification

The Windows workflow runs the frozen executable's `--self-test` path, exercises all four charts, pin/popout behavior, CSV/PDF/PNG output, and history/preferences restart. It silently installs into a fresh temporary directory, repeats the installed launch checks, uninstalls, and verifies that the program is removed while user data remains.

This confirms basic package behavior; it is not a multi-hour workload test or a claim of a signed release.

## Implementation sources

- [PyInstaller onedir/windowed options](https://pyinstaller.org/en/stable/usage.html).
- [Inno Setup per-user privileges](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
- [SQLite transactions and parameter binding in Python 3.11](https://docs.python.org/3.11/library/sqlite3.html).
- [SQLite database page limits](https://www.sqlite.org/pragma.html#pragma_max_page_count).
- [Atomic file replacement](https://docs.python.org/3.11/library/os.html#os.replace).
