# GPU Live Graphs 0.5.0 preview

This preview follows the requested development order: Windows packaging, persistent history, saved preferences, then stability checks. Tray monitoring, alerts, and process details are deferred.

## Included

- Portable Windows x64 app and per-user installer. Python/Tk/Pillow are bundled.
- Start menu shortcut, optional desktop shortcut, and uninstall support.
- Background SQLite history: up to 24 hours, a 128 MB database cap, up to 4,000 recent samples restored into the 1-hour interactive view.
- Full retained-history CSV export for the selected GPU.
- Saved per-GPU colors/styles/focus, filters, history range, zoom, always-on-top, window geometry, and up to 12 detached views.
- UUID-based filter restoration, atomic preferences writes, corrupt-file backup, and off-screen geometry correction.
- Per-user logs, exports, captures, history, and preferences survive upgrades and uninstall.

## Validation

The release workflow tests Python 3.11/3.14 and gates these packages on frozen rendering/export/restart checks plus isolated installation, installed launch, and uninstallation. See the workflow run for this tag's commit and [the verification record](VALIDATION-0.5.0.md).

## Limits

- Packages are unsigned.
- Pins are not restored after restart. Preferences are saved every five seconds and at normal shutdown.
- Archive retention/size are fixed in this first implementation. The database cap does not include exports, captures, logs, or SQLite's temporary transaction journal.
- Long workload soak testing and a full mixed-DPI monitor matrix remain open. The earlier abrupt exit has not been conclusively reproduced or attributed to a specific cause.

Use the installer EXE, or extract the entire portable ZIP before running its EXE. Keep the `_internal` folder beside it. The NVIDIA driver is still required.
