# GPU Live Graphs 0.8.0 preview

Add CPU, RAM and storage monitoring underneath the original four GPU graphs, while preserving the independent Replay tab.

Download **GPU-Live-Graphs-0.8.0-Setup.exe**, or extract the complete **Windows-x64.zip** and run the EXE. Python and psutil are bundled. Close older copies before updating; existing GPU history and preferences are retained.

## New resource views

- Four configurable circular gauges beneath the GPU rack, with Ring, Pie and Arc styles. Minimize them to numerical readings.
- Expandable CPU, RAM and storage detail graphs, plus a separate System tab with more room for logical CPU traces.
- Scrollable frosted sensor menus support individual choices, first-four/first-eight presets, or all logical processors. Choose existing Line, Filled, Gradient, Dashed and Hatched styles; edit colors with the palette or hex/hue controls.
- A collapsible occupancy heatmap colors recorded time in each range from yellow through red to purple. Clock-frequency bands adapt to the observed range so small GHz differences remain visible. Gaps and missing samples contribute no dwell time.
- Gauge choices, collapse state, detail expansions, sensor selections, colors, styles and heatmap options survive restart.

## Responsiveness and accuracy

- Gauges, heatmaps and resource graphs draw on the bounded background renderer. New data does not continually invalidate an otherwise usable pending frame.
- The subtle background gradient now uploads in small UI tasks and skips offscreen panels. Popup interactions reuse the blurred underlay until the dashboard refreshes it, avoiding repeated allocation of an entire tall rack.
- Capacity gauges use reported installed RAM or logical-volume totals. Disk I/O rates use each counter's own elapsed time, including a drive that disappears and returns.
- CPU percentage sampling is primed on the worker. Recorded system snapshots are immutable. Pause freezes both GPU and system timelines; Replay remains independent.

## Scope and validation

Logical CPU utilization is available per logical processor. CPU GHz is the system-reported clock, **not a per-thread clock measurement**. RAM is system-wide; physical-disk throughput and filesystem-volume capacity are distinct.

System data is currently retained only in memory, up to 4,000 snapshots. The 24-hour SQLite archive, CSV/PDF exports and Replay continue to cover GPU data. System graphs use a five-minute range; their selection/style controls do not imply the GPU graphs' pin/zoom/export features.

The release workflow runs Windows tests on Python 3.11 and 3.14, then builds and checks the portable app, installation and removal. The frozen self-test also imports the real psutil extension and checks resource graphs, gauges, heatmap and preference restoration. Local Linux Tk tests exercise the same UI code, with Windows-specific tests left to CI. Multi-hour physical Windows GPU/system monitoring and mixed-DPI testing remain open. Packages are unsigned previews.

See the [system resource guide](https://github.com/walladanger/New-gpu-monitor-4way4the4play/blob/main/docs/SYSTEM-RESOURCES.md) and the [validation record](https://github.com/walladanger/New-gpu-monitor-4way4the4play/blob/main/docs/VALIDATION-0.8.0.md).
