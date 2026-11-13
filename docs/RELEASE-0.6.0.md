# GPU Live Graphs 0.6.0 preview

This preview repairs three reproduced interaction failures and adds shared GPU appearance controls, clock-time axes, expanded history choices, and per-session debugging logs.

Download **GPU-Live-Graphs-0.6.0-Setup.exe**, or extract the complete **Windows-x64.zip** and run `GPU-Live-Graphs.exe`. Python is bundled; the NVIDIA driver is required. Close older copies before updating. Existing saved history and preferences are retained.

## Changes

- GPU buttons remain mapped during refresh, preserving a press/release across a redraw.
- A bounded background worker draws graphs while the main thread processes input. New appearance requests replace pending stale frames rather than building an unbounded queue.
- Tk images and variables collected by a worker defer their cleanup to the UI thread. This fixes a reproduced deadlock while repeatedly closing and reopening graph windows.
- Click anywhere near a visible line segment to pin the nearest real endpoint sample. Values are never interpolated from the pointer position.
- **Global GPU settings** is on by default. Color, style, transparency and emphasis follow a GPU across all main and detached windows. Uncheck it for local edits; rechecking returns to the shared appearance.
- The GPU menu adds **Transparency**, from opaque to invisible. It fades the line and fill without fading the grid. Hex input and the five existing line/shading styles remain.
- Each graph has a small **circled clock** button to switch relative ages to local timestamps, preserving zoom and pan. Time mode is saved separately for each view.
- History offers **30 seconds; 1, 2, 5, 10, 15, 30, or 45 minutes; and 1 hour**. Menus use a 50% dark tint with a blur of application content underneath.
- **Settings** exposes the debugging-log folder, Browse, Save folder, Open log and Log folder controls. Every launch gets unique session/native files, starting before GUI imports. The default is `D:\DEBUGGING LOGS` if that drive exists, otherwise local app data. An unavailable destination falls back to local logging.
- Saving another log destination copies this session immediately and at normal shutdown; the next launch logs there from the start. Logs record startup phases, input outcomes, slow frames, UI delays and exceptions. They remain on your computer.
- If startup or the UI stops responding for about 30 seconds, the native diagnostic file records thread stacks for investigation.
- Eight refreshed screenshots show the actual app with clearly marked synthetic data.

## Validation and limits

The Windows release workflow gates publication on Python 3.11/3.14 tests, source packaging, frozen application launch, exports, persisted state, installation and uninstallation. The packaged smoke test uses the background renderer.

Read the [0.6.0 validation record](https://github.com/walladanger/New-gpu-monitor-4way4the4play/blob/main/docs/VALIDATION-0.6.0.md) for local checks and remaining qualification work. Short checks do not establish that every intermittent click problem or abrupt exit is resolved. Multi-hour workloads and the full mixed-DPI matrix remain open. Packages are currently unsigned. Tray, alerts and process/runtime insights remain deferred.
