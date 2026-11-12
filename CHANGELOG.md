# Changelog

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
