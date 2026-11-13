# Changelog

## 0.6.0 preview — November 13, 2026

- Keep GPU buttons mapped during refresh so presses survive a redraw.
- Draw graphs on a bounded background worker; apply Tk images on the input thread and discard stale appearance frames.
- Defer worker-triggered cleanup of Tk images/variables to their owning UI thread, repairing a reproduced resize/reopen deadlock.
- Accept clicks on visible line segments, selecting actual recorded samples rather than interpolated values.
- Add default-on global GPU settings across main/detached windows, optional local edits, and a transparency slider.
- Save global scope, transparency and per-window relative/clock axis choices.
- Add a small circled clock toggle with aligned local timestamps, including seconds for shorter ranges and dates across midnight.
- Expand History to nine ranges from 30 seconds through one hour; use 50% tinted, locally blurred menus.
- Start unique session/native-fault logs before GUI imports, with dashboard folder selection and open-log controls.
- Refresh eight actual-UI screenshots using explicitly synthetic readings.
- Further long workload and mixed-DPI qualification remains open.

## 0.5.0 preview · November 12, 2026

- Add a portable Windows x64 app and per-user installer with install/uninstall verification.
- Move writable data to `%LOCALAPPDATA%\GPU Live Graphs`.
- Persist 24 hours of query history in a bounded background SQLite archive; restore up to an hour and export older retained rows to CSV.
- Save preferences and detached views with UUID-based selection and monitor-aware geometry fallback.
- Add corrupt-file preservation, atomic preference writes, bounded worker queues, and source/frozen restart checks.
- Add repeatable stability checks. Earlier abrupt exits and the full mixed-DPI matrix remain open.
- Defer tray, alerts, and process details until the next visual direction is supplied.

## Repository/documentation foundation · November 12, 2026

- Publish the standalone GPU Live Graphs source separately from GPU-Monitoring.
- Add a colorful GitHub landing README and six actual-UI demo screenshots.
- Add a feature walkthrough, detailed user guide, design findings, and prioritized roadmap.
- Preserve the repository's existing MIT license.
- Add screenshot reproduction, documentation validation, and Windows test/source-package workflow.

The application version remains **0.4.1**; this foundation does not claim additional monitoring features.

## 0.4.1

- Replace the Python native-window callback with real Tk resize grips.
- Repair edge/corner resize and maximize/restore, including final quick-drag positions.
- Clear old grid sizing when switching to vertical panels.
- Add local crash/error logs and redraw-loop recovery.
- Abrupt exits reported during earlier testing remain under investigation.

## Earlier iterations

The four-panel interface, sample pins, independent graph windows, focus/style menus, exports, time zoom, slim scrolling, and subtle animated background were developed through 0.2–0.4.0. This repository starts from the 0.4.1 standalone source; earlier ZIP packages are not a complete Git history here.
