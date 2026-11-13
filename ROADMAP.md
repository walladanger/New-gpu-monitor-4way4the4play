# GPU Live Graphs · Roadmap

Reviewed November 13, 2026 against standalone **0.6.0 preview**. This roadmap belongs to this repository, not the separate C# GPU-Monitoring app. Priorities describe recommended order, not delivery dates.

## Current requested order

| Order | Work | Status |
| --- | --- | --- |
| 4 first | Windows EXE and installer | Implemented; portable/frozen/install/uninstall checks gate release |
| 3 next | Persistent history | Implemented: 24h archive, 128 MB database cap, 1h graph restore, saved-history CSV |
| 2 next | Saved preferences | Implemented: atomic JSON, UUID-based views, geometry recovery, detached views |
| 1 next | Stability | 100-cycle synthetic and 180-second live checks passed; multi-hour and full mixed-DPI qualification remain open |
| 5 later | Tray, alerts, process details | Deferred at the user's request pending visual ideas and screenshots |

## Working now

- [x] Shared NVIDIA sampler and UUID-based GPU identity.
- [x] Four graphs with actual GPU names and numbered duplicates.
- [x] Wide grid, full-width vertical stack, and conditional scrollbars.
- [x] Frameless resize/maximize/restore and subtle animated background.
- [x] Recorded-sample pins, four-metric inspector, and comparisons.
- [x] Default-on global GPU focus/appearance, optional local scope, editable colors, five visual styles and transparency.
- [x] Relative/clock axis toggle per graph and nine history choices.
- [x] Bounded background graph drawing, stable GPU buttons, segment click selection, and per-session diagnostic logs.
- [x] Wheel zoom, timeline panning, and independent detached views.
- [x] Pause, CSV/PDF exports, and graph PNG capture.
- [x] Stale/error states, sampling retries, redraw recovery, local crash logs.
- [x] GitHub landing page, eight real-UI demo captures, and feature walkthrough.
- [x] Windows CI on Python 3.11 and 3.14, with source ZIP and SHA-256 artifact.
- [x] Bundled Windows x64 portable app and per-user installer.
- [x] Background SQLite history with restart recovery and retained-history CSV.
- [x] Saved colors/styles/filters/history/geometry and detached views.

## P0 · Confidence before expansion

| Item | Done when | Current state |
| --- | --- | --- |
| Investigate abrupt exits | Reproduce or obtain useful logs; identify and verify a cause | Open; resize fixed, abrupt exit not reproduced |
| Hardware soak test | Several hours of idle/load/transitions on dual 3090 + 4070; no unbounded memory growth or lost refresh | Not yet run |
| Multi-monitor/DPI matrix | All grips, monitor moves, maximize, minimize/restore, and missing-display recovery pass on mixed DPI | Basic controls checked; full matrix pending |
| Windows CI | Tests run and a source ZIP is produced from the same commit | Passed on Python 3.11 and 3.14; source/checksum artifact uploaded |
| Release qualification | Versioned notes, checksums, clean-machine launch, and dependency review | Pending |

**Current focus:** complete stability qualification of the new packaging, archive, and preference paths. Keep item 5 deferred.

## P1 · Daily usability and installation

| Item | Acceptance criteria | Suggested approach |
| --- | --- | --- |
| Saved preferences | Restart restores valid geometry, filter, history, colors/styles; missing cards/displays fall back safely | Implemented; includes corrupt-file preservation |
| Session layout | Detached windows restore without duplicate collectors | Implemented, up to 12 views; reset/opt-out controls remain future work |
| Persistent history | Survives restart; bounded retention/storage; missing values and UTC timestamps retain meaning | Implemented with fixed 24h/128 MB limits; configurable limits and longer graph browsing remain future work |
| Windows package | Runs without installing Python; installation/removal preserves user data | Implemented; broader clean-machine coverage and signing remain open |
| Startup diagnostics | Session files before GUI imports, user-selected location, dashboard access | Implemented; hard native exits still need field logs |
| Keyboard/accessibility | Useful names for icons, visible focus, keyboard access to menus/pins/exports/zoom | Verify Windows UI Automation and Tk behavior |
| Export destination | User selects folder/name; cancel leaves no partial file | Keep toolbar export placement |

## P2 · Monitoring that stays out of the way

Tray monitoring, alerts, and process details in this section are deferred until the user's next ideas/screenshots are available.

- [ ] Tray quick view with explicit quit.
- [ ] Optional temperature/VRAM/power thresholds with debounce and cooldown.
- [ ] Adjustable polling interval with an overhead budget.
- [ ] GPU process list, showing unavailable data honestly under Windows WDDM limitations.
- [ ] Optional NVML backend behind the existing reading model; validate before replacing `nvidia-smi`.
- [x] Absolute local-time axis labels.
- [ ] Pan-to-live and optional linked graph timelines.
- [ ] Pin list, clear-all action, comparison export, and keyboard selection.

## P3 · Runtime insights and broader hardware

- [ ] Active requests, tokens/sec, and TTFT through real runtime/server adapters. These cannot be derived from GPU utilization.
- [ ] Optional CPU/RAM context while preserving the four default GPU panels.
- [ ] AMD/Intel collectors with explicit capabilities and validation.
- [ ] Evaluate GPU Taskman integration separately. There is no current dependency or integration.

## Design guardrails

Preserve the four data panels and measurement hierarchy. Stack narrow layouts vertically. Keep GPU colors/styles/transparency consistent globally by default; let the user explicitly opt into local edits. Use text/shape/style alongside color. Keep overlays dark, translucent, and locally blurred. Pin recorded samples rather than interpolated values; keep missing values distinct from zero. Label synthetic demonstrations clearly.

## Decisions still needed

Packaging uses PyInstaller plus Inno Setup. Initial archive limits are 24 hours and a 128 MB database cap. Signing, user-configurable archive limits, and later alert delivery choices remain open. Unchecked work is not included in version 0.6.0.
