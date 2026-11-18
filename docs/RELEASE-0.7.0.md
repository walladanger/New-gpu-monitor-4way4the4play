# GPU Live Graphs 0.7.0 preview

This preview builds on 0.6.0, adding a separate four-panel Replay workspace for real recorded GPU samples, restoring narrow-layout scrolling, and keeping the existing Live monitor intact.

Download the Windows x64 installer or portable ZIP from this version's release page. Close older copies first. The installer keeps saved preferences, SQLite history, and locally stored session logs. Packages contain Python and Pillow; an NVIDIA graphics driver with nvidia-smi is required.

## Added

- Dedicated **Live** and **Replay** tabs with separate data contexts. Live NVIDIA collection continues while Replay is open; switching tabs never replaces recorded readings with current readings.
- **Load last recording** selects the newest completed SQLite session, falling back to an active-session snapshot only when no completed recording exists.
- **Snapshot this session** explicitly freezes a view of the recording still in progress.
- Replay at original recorded time intervals with Play/Pause, Restart, End, a scrubber and speeds from 0.25x to 4x. No interpolation, extrapolated GPU values, auto-loop, or fabricated frames.
- Four interactive graphs using the existing chart renderer, recorded local-time axes by default, independent zoom, pins and GPU selection.
- Missing/stale GPU values remain unavailable; replay ends at the final archived sample. The SQLite reader runs on its existing background worker.
- Narrow layouts expose vertical scrolling for both Live and Replay.
- Graphs recover from transient rendering failures without permanently caching a blank frame; verified with a regression test.

## Data limits

Only queried GPU sensor samples and their original timestamps were recorded. The app cannot reconstruct unrecorded frames, old UI state, external workloads or processes. The archive is retained for up to 24 hours subject to its 128 MB storage cap. Older samples may already have expired.

## Validation and remaining work

Windows CI runs unit/component tests on Python 3.11 and 3.14, checks documentation, builds a portable ZIP and a per-user installer, and exercises frozen launch, Replay restore, exports, history/preferences preservation, installation and uninstallation.

This is a **preview**, not a hardware-soak qualification. Multi-hour dual-3090/4070 load sessions, mixed DPI/multi-monitor transitions, installer upgrades on several real Windows machines and package signing remain open. Read [Replay design and fidelity](https://github.com/walladanger/New-gpu-monitor-4way4the4play/blob/main/docs/REPLAY.md) and [roadmap](https://github.com/walladanger/New-gpu-monitor-4way4the4play/blob/main/ROADMAP.md).
