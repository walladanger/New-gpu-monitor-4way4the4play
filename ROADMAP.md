# GPU Live Graphs · Roadmap

Reviewed November 12, 2026 against standalone Python **0.4.1**. This roadmap belongs to this repository, not the separate C# GPU-Monitoring app. Priorities describe recommended order, not delivery dates.

## Working now

- [x] Shared NVIDIA sampler and UUID-based GPU identity.
- [x] Four graphs with actual GPU names and numbered duplicates.
- [x] Wide grid, full-width vertical stack, and conditional scrollbars.
- [x] Frameless resize/maximize/restore and subtle animated background.
- [x] Recorded-sample pins, four-metric inspector, and comparisons.
- [x] Per-panel GPU focus, editable colors, and five visual line styles.
- [x] Wheel zoom, timeline panning, and independent detached views.
- [x] Pause, CSV/PDF exports, and graph PNG capture.
- [x] Stale/error states, sampling retries, redraw recovery, local crash logs.
- [x] GitHub landing page, six real-UI demo captures, and feature walkthrough.
- [x] Windows CI on Python 3.11 and 3.14, with source ZIP and SHA-256 artifact.

## P0 · Confidence before expansion

| Item | Done when | Current state |
| --- | --- | --- |
| Investigate abrupt exits | Reproduce or obtain useful logs; identify and verify a cause | Open; resize fixed, abrupt exit not reproduced |
| Hardware soak test | Several hours of idle/load/transitions on dual 3090 + 4070; no unbounded memory growth or lost refresh | Not yet run |
| Multi-monitor/DPI matrix | All grips, monitor moves, maximize, minimize/restore, and missing-display recovery pass on mixed DPI | Basic controls checked; full matrix pending |
| Windows CI | Tests run and a source ZIP is produced from the same commit | Passed on Python 3.11 and 3.14; source/checksum artifact uploaded |
| Release qualification | Versioned notes, checksums, clean-machine launch, and dependency review | Pending |

**Recommended next feature:** saved preferences after the stability checks. It improves every launch without introducing another telemetry backend.

## P1 · Daily usability and installation

| Item | Acceptance criteria | Suggested approach |
| --- | --- | --- |
| Saved preferences | Restart restores valid geometry, filter, history, colors/styles; missing cards/displays fall back safely | Versioned JSON, atomic saves, UUID keys |
| Session layout | Optional detached windows restore without duplicate collectors; reset-layout command works | Opt-in session restore |
| Persistent history | Survives restart; explicit retention/disk budget; missing values and UTC timestamps retain meaning | SQLite with bounded reads/writes |
| Windows package | Clean Windows machine runs without installing Python | Portable EXE first, installer next |
| Startup diagnostics | Clear errors for missing Python/Pillow/driver; easy access to diagnostics | Avoid silent startup failures |
| Keyboard/accessibility | Useful names for icons, visible focus, keyboard access to menus/pins/exports/zoom | Verify Windows UI Automation and Tk behavior |
| Export destination | User selects folder/name; cancel leaves no partial file | Keep toolbar export placement |

## P2 · Monitoring that stays out of the way

- [ ] Tray quick view with explicit quit.
- [ ] Optional temperature/VRAM/power thresholds with debounce and cooldown.
- [ ] Adjustable polling interval with an overhead budget.
- [ ] GPU process list, showing unavailable data honestly under Windows WDDM limitations.
- [ ] Optional NVML backend behind the existing reading model; validate before replacing `nvidia-smi`.
- [ ] Absolute time labels, pan-to-live, and optional linked graph timelines.
- [ ] Pin list, clear-all action, comparison export, and keyboard selection.

## P3 · Runtime insights and broader hardware

- [ ] Active requests, tokens/sec, and TTFT through real runtime/server adapters. These cannot be derived from GPU utilization.
- [ ] Optional CPU/RAM context while preserving the four default GPU panels.
- [ ] AMD/Intel collectors with explicit capabilities and validation.
- [ ] Evaluate GPU Taskman integration separately. There is no current dependency or integration.

## Design guardrails

Preserve the four data panels and measurement hierarchy. Stack narrow layouts vertically. Keep per-GPU controls local to the selected chart. Use text/shape/style alongside color. Keep overlays dark, translucent, and locally blurred. Pin recorded samples rather than interpolated values; keep missing values distinct from zero. Label synthetic demonstrations clearly.

## Decisions still needed

Packaging technology, persistence retention defaults, and alert delivery channels remain open. Unchecked work is not included in version 0.4.1.
