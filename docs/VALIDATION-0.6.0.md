# 0.6.0 validation — November 13, 2026

Local Windows checks used Python 3.14.7 and Pillow 12.3. No GPU clocks, power limits, driver settings or workloads were changed. Live sampling queried the installed NVIDIA driver.

| Check | Result |
| --- | --- |
| Complete unit/component suite | 67 tests passed |
| Slow-render interaction regression | Redraw request stays under the 120 ms test limit while each graph draw is deliberately delayed 150 ms; a real Tk press/refresh/release and subsequent pin are accepted |
| GPU buttons during refresh | No Unmap events across the tested redraws |
| Segment selection | Click between vertices resolves to an actual recorded endpoint sample |
| Bounded rendering | Latest settings replace pending work; stale appearance frames do not apply; live frames are not starved; closed windows receive no late presentations |
| Worker garbage collection | Image/variable finalizers queue disposal for the UI thread; no worker-side Tcl wait |
| Appearance and preferences | Global default, local opt-out, detached propagation, slider endpoints, restart and UUID scope passed |
| Clock labels | Aligned local times, panned range, midnight dates, view preservation and per-window restoration passed |
| Session diagnostics | Early bootstrap without Tk imports, unique launches, selected destination, shutdown copies, relative-path rejection and unavailable-folder fallback passed |
| Source application smoke test | Four charts; startup log/settings; maximize/restore; pins/popout; CSV/PDF/PNG; history/preferences restart passed |
| Synthetic resize/reopen exercise | 100 cycles, 83.78 seconds, 3 synthetic GPUs and about 3,600 samples; no callback/storage errors; 973 completed frames |
| Live NVIDIA exercise | 120.08 seconds, 10 resize/reopen cycles, 3 detected GPUs, 119 samples; no callback/storage errors; 2,788 completed frames |
| Documentation | Eight actual-app screenshots, local Markdown links and SVG banner validated |
| Source package | ZIP built and integrity checked; excludes logs, user captures and build output |

The live exercise recorded an average redraw/request-and-update duration of 7 ms and a maximum of 71 ms. The maximum individual worker frame draw was 6 ms with that short history. One UI heartbeat delay exceeded 100 ms; the maximum was 107 ms. These are development-machine observations, not a frame-rate guarantee or hardware benchmark.

The larger synthetic exercise includes continuous geometry/maximize/popout changes and records higher costs: average request-and-update duration 259 ms, maximum 538 ms; maximum heartbeat delay 392 ms. It is evidence against the reproduced deadlock, not evidence of uniformly smooth resizing with a full hour of data.

## Reproduced causes and fixes

1. Refreshes unconditionally removed and re-added GPU name buttons. Keeping unchanged buttons mapped preserves an in-progress press/release.
2. Pillow drawing ran on the input thread. A bounded worker now draws immutable scene inputs, while the UI applies images and processes input.
3. Hit testing only considered sample vertices. A spatial index now accepts visible line segments and returns a real endpoint sample. Gaps and invisible traces are not selectable.
4. The new stress check exposed cyclic garbage collection invoking Pillow's default Tk image destructor on the rendering worker. A thread stack captured that exact wait. App-owned image/variable wrappers now defer disposal to the owning UI thread, with a regression test that forces worker-side collection.

The Windows release workflow independently runs Python 3.11/3.14 tests and gates portable/installer publication on frozen, installed and uninstall checks. See the commit's Actions result for that separate qualification.

## Still open

Multi-hour idle/load transitions, the full mixed-DPI/multi-monitor matrix, broader clean-machine qualification and signing remain open. The supplied video was not retrievable in this session, so it was not used as validation evidence. The fixes address reproduced failures; remaining field symptoms should be matched to the new session logs. Tray, alerts and process/runtime features remain deferred.
