# Replay tab — sensor recording playback (development branch)

The Replay feature is separate from the Live dashboard and shares only the
existing read-only graph engine. **Introduced in 0.7.0 preview; not available in 0.6.0.**

## How it works

1. Select **Replay** beside the **Live** tab.
2. Select **Load last recording** (loading is asynchronous, not a blocking
   SQLite query on the Tk input thread).
3. **Load last recording** selects the most recent completed session; if none
   exists, it falls back to the available current session. **Snapshot this
   session** explicitly loads the ongoing recording. Both load paused at the
   first retained sample. New live readings never silently alter loaded Replay.
4. Use **Play**, **Pause**, **Restart**, **End**, the timeline slider, and the
   speed choices (0.25x–4x). Playback stops automatically at the exact last
   retained sample; it does not loop or invent data.
5. Each of the same four charts can be inspected, zoomed, and pinned
   independently. Graph labels default to recorded local clock time. The
   displayed GPU readings are from the exact recorded snapshot.
6. Select **Live** to return to current NVIDIA driver readings. Recording
   continues independently while Replay is visible.

## Data fidelity and coverage

- The SQLite archive already records GPU UUID/name, utilization, VRAM
  used/capacity, temperature, board power/power limit, and wall timestamps.
- Samples are played at their *original* wall-clock intervals. No
  interpolation or estimated GPU measurements are introduced between records.
- A missing reading stays missing, not zero. A held reading older than 1.5
  seconds is displayed as unavailable, and gaps in graph data remain gaps.
- Archived sessions are identified by their existing SQLite session column.
  Replay chooses the last *completed* session by default; a separate button
  makes a read-only snapshot of the active session.
- History is subject to the existing **24-hour retention**, **128 MB archive
  cap**, and row retention limits. If the earliest part of a recording has
  expired, Replay starts with the earliest retained sample. It cannot recover
  data that was not saved.
- Stored readings are immutable during replay. The dashboard does not
  capture video frames, prior window positions, graph style changes, clicks,
  external workload activity, or GPU driver events; these cannot be recreated
  from sensor samples.
- In non-persistent demo/test mode, Replay operates on the current in-memory
  graph history and labels it explicitly as an in-memory preview.

## Implementation boundaries

- history_store.py: latest-session lookup and restore happens on the
  existing background SQLite worker; there is no schema migration.
- replay.py: pure, deterministic finite playback and recorded-data slicing.
- dashboard.py: dedicated Replay tab, four views, scrubber and controls.
  Main Live view, GPU collector, exports, detached windows, and the existing
  renderer remain in place. Live updates never overwrite a paused replay.

## Verification

The project's normal Windows unit suite now covers original timing,
scrubbing, missing values, exact final sample, newest recording selection,
and Live/Replay view isolation. The frozen Windows self-test also switches
tabs and checks the persisted last session.

Additional validation on a user's own hardware remains necessary: long
sessions, simultaneous recording during replay, app restart under a large
archive, mixed DPI/monitor moves, and installer migration from 0.6.0.
