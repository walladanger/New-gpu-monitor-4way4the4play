# 0.8.0 validation — November 18, 2026

The system-resource draft previously failed the same responsiveness regression on both Windows Python versions: one redraw took approximately 125–167 ms against the existing 120 ms limit. An isolated Linux Tk reproduction also failed, at approximately 197 ms. A new thread-ownership test independently caught gauges drawing on the input thread.

## Repairs

- Queue dial and heatmap painting on the bounded renderer; keep completed-frame presentation on Tk's owning thread.
- Separate presentation settings from moving data/timestamps so new samples cannot perpetually invalidate slow resource frames.
- Spread ambient background uploads over short event-loop tasks, skip offscreen branches, and stop the tasks when windows close.
- Crop popup backdrops to their visible intersection and reuse their blur during interaction; normal dashboard refreshes update it.
- Bound sensor discovery during refresh, preserve explicit selections through temporary sensor loss, and retain settings across restart.
- Use installed capacity totals, immutable readings and per-device counter timestamps. Prime initial CPU percentages and freeze system views with Pause.

The original interaction regression and the added drawing-thread test pass after the fixes; the existing time limit was retained. Local profiling of the reproduction reduced the instrumented redraw path from approximately 778 ms to 53 ms. These profile observations include instrumentation overhead and are not a frame-rate guarantee.

## Checks

The local Python 3.12/Pillow 12.3 Tk suite passed **100 tests**, with the **two Windows-only tests skipped**. It includes archive/Replay and GPU regressions, resource sampling, frozen snapshot values, long sensor menus, hex editing, mode selection, pause, preference restart, correct capacity scales, missing gaps and returning-disk rates. Three actual-UI synthetic resource captures were produced and inspected.

The Windows workflow independently gates packaging on Python 3.11/3.14 tests. The frozen and installed smoke tests now exercise bundled psutil, system charts, four gauges, the occupancy heatmap and saved appearance, in addition to GPU rendering, exports, SQLite restart and Replay. See PR #3 and the release commit's Actions result for those separately executed Windows checks.

No live NVIDIA hardware was available in this Linux session. Physical Windows monitoring for several hours, mixed DPI, removable/network drive behavior under failures and broader clean-machine coverage remain open. System telemetry is not yet included in the GPU SQLite/Replay archive. Screenshots and synthetic tests are not presented as hardware performance measurements.
