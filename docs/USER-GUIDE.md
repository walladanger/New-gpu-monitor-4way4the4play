# GPU Live Graphs 0.4.1

Four live NVIDIA graphs: GPU usage, VRAM, temperature and board power. Written in Python, with Tkinter windows and Pillow graph rendering.

## Start

Extract the entire folder and double-click **Start.cmd**, or **Launch.pyw** if Python handles .pyw files. Close the older version when you are ready; launching the update does not transfer that running instance's history.

Requirements: Windows 10/11, Python 3.11+ with tkinter, Pillow 12.x, and an NVIDIA driver with nvidia-smi. Python 3.14 and Pillow 12.3 are already available on the development machine. No administrator access, CUDA Toolkit, API key or network connection is needed to run it.

On another machine, install Pillow with `python -m pip install -r requirements.txt` if needed.

## Frameless appearance

The main app and separate graph windows use a custom dark header with minimize, maximize/restore and close buttons. Drag the heading to move a window, double-click it to maximize/restore, and drag window edges/corners to resize. All eight resize grips have their own input handlers. The window keeps a taskbar entry, and maximizing fits the monitor work area. This version uses Tk-managed movement and resizing; it does not install a Python callback into the native Windows window procedure.

A very low-contrast horizontal gradient drifts across the app and its panels on an approximately two-minute cycle. Highlights are limited to four or five RGB levels above the existing background. The gradient shares a window-wide position, so its lighting stays aligned across the panels. It uses the existing redraw loop and respects Windows' client-area animation preference. Graph readings, pin coordinates and GPU color choices are independent of this animation.

## Four panels, responsive layout

The original four measurements, colors, grids and live values remain. A wide window uses the 2 x 2 grid. Below approximately 1,060 pixels of graph-area width, all four stack vertically. The graph area scrolls so the panels remain readable rather than being squeezed down. The GPU labels and toolbar also wrap as needed.

## GPU names are buttons

Names show the actual card models. Identical cards are distinguished as **RTX 3090 #1** and **RTX 3090 #2**, with stable NVIDIA UUIDs identifying them internally. The third card is **RTX 4070**.

- Click a GPU name above a graph to brighten/thicken that card's line, dim the others in that graph, and open its frosted quick menu.
- Click the same name again to restore all lines.
- Click a name in the top legend to focus that GPU across all four main panels.
- Use the GPU dropdown to show just one card instead of emphasizing it.

## Lock on to actual data

Left-click close to a plotted line to select the nearest actual recorded sample. The app does not invent a value between samples. A lettered marker and vertical guide track the selected timestamp as the live graph scrolls.

The frosted inspector shows the selected card's name, local timestamp to milliseconds, and all four measurements from that same driver query. Its values retain the precision supplied by the driver. VRAM uses GiB, converted from MiB; the regular live headers remain rounded for readability.

Pin several points in one graph to compare them. Each has its own letter and recorded values. The comparison section shows changes in all four metrics and elapsed time from the first pin to the most recently added pin. Load changes use percentage points (pp). When comparing different cards, each row identifies the card.

Right-click a marker or its inspector row to remove that individual pin. Pins otherwise remain attached to their samples until they scroll outside that window's selected history range. Pausing freezes the timeline and pins. A hidden card's pins return when you select All GPUs, provided their timestamps are still in range.

Drag the inspector header to move it out of the way. Use the mouse wheel inside it to scroll through pins and comparisons. Over the graph, the wheel zooms; Shift+wheel scrolls the main page.

The inspector is semi-transparent with a Gaussian blur of the actual live graph pixels underneath. It is rendered from the application's own chart scene; no desktop capture or access to other windows is involved.

## Separate graph windows

Each main panel has a small **square-and-arrow icon** in its top-right corner. The icon is 25% smaller than the initial icon design, with its click area retained. The new window contains a live copy, leaving all four original panels in place. It shares the existing sampler and recorded history, while its GPU selection, history range, line focus, colors, line styles and pins are independent. Existing view settings and pins are initially copied. Closing it leaves the main dashboard running. Pause/resume applies to all windows.

## Quick menu and control styling

The Show and History selectors are custom dark, rounded controls. Their choice lists and GPU quick menus use the same semi-transparent black tint and background blur as the pin inspector. Click elsewhere or press Escape to dismiss a menu.

A GPU name inside a panel opens a menu that applies only to that GPU in that panel:

- Type or paste a color into the hex field. It accepts #RRGGBB or #RGB, with the leading # optional. Valid complete codes preview immediately; Enter confirms the normalized code. Invalid or partial input leaves the last valid graph color intact.
- Drag the color slider to change its hue; the hex field stays synchronized.
- Choose Line, Filled, Gradient, Dashed or Hatched using the visual preview tiles. Gradient fades the fill toward the baseline; Hatched uses diagonal shading. These are presentation styles; pinning still selects actual samples.

Closing the menu leaves the chosen color/style and line emphasis in place. Clicking the same GPU name again restores equal line brightness.

## Zoom and timeline navigation

Roll the mouse wheel over a graph to zoom its time axis in or out around the pointer. The small corner plus/minus buttons provide the same control. Click the zoom multiplier, such as 2.0x, to reset to the full selected History range. Maximum zoom retains a two-second time span; it cannot create finer measurements than the recorded samples.

A slim, arrowless horizontal timeline scrollbar appears only while that graph is zoomed in. Drag it to pan within the selected History range. Resetting zoom removes it. Historical axis labels show their age relative to the live timeline, rather than labelling past data as now.

The main page's matching vertical scrollbar appears only when the four panels overflow the window, such as in a narrow stacked layout. Shift+wheel scrolls that page instead of zooming a graph. Wheel events inside the pin inspector scroll its details.

Pins remain recorded while you zoom or pan, and return when their timestamps are visible again. They expire when time carries them outside the selected base History range. The live headers continue to show the latest readings while you inspect older graph data.

## CSV and PDF

Open **Export** in the main toolbar, choose a data window and GPU, then select CSV or PDF. Separate graph windows have their own toolbar Export menu. Files are saved in the `exports` folder beside the app; the main status bar reports the filename. CSV includes local and UTC timestamps, GPU identity, all four measurements, original MiB values and capacity/power limits. Unavailable readings are blank, and measured zero remains zero.

PDF contains a graph and summary followed by tables of every actual sample in that selected GPU's visible time range. It is a rendered visual report; use CSV for machine-readable values. Neither export invents intermediate samples or includes a different GPU's readings.

## Save an image for annotations

Open **Export → Save all graphs as PNG** to capture all four graphs, including names, live values and visible pin details, in the `captures` folder alongside the app. It follows the current grid/vertical arrangement. In a separate graph window, use **Export → Save graph as PNG**. The status bar reports the saved filename. This provides an alternative to taking a screen grab.

## Source of the readings

This is an independent desktop companion inspired by [Scott Hanselman's GPU Taskman](https://github.com/shanselman/gputaskman). It does not read GPU Taskman or include its code. Measurements come directly from NVIDIA's driver via nvidia-smi once per second, in one shared background sampler regardless of how many windows are open.

This version provides NVIDIA device-level graphs. GPU Taskman's process/model inspector, AMD support and KV-cache analysis are not integrated. Power is GPU board power, not wall-socket power. Timestamps describe the completed driver query; different sensors may have their own measurement intervals.

Unsupported readings display as unavailable, never as a measured zero. Driver errors trigger retries and visible status messages. Missing readings and paused intervals appear as gaps. History remains in memory for up to about 15 minutes and is discarded on exit.

## Validation and troubleshooting

### 0.4.1 resize and stability fix

The 0.4.0 resize regression was reproduced through Windows' actual pointer target: all four edges and four corners were treated as client content, so the native resize hook did not receive the intended input. The regression test now locates the real widget under each edge/corner and verifies that dragging it changes the window dimensions. Header maximize/minimize controls are tested through their button commands.

The native window-procedure hook was removed. Fast drags also commit their final position on mouse release, and switching to a vertical layout clears the old grid-column sizing so each panel fills the available width. A redraw exception now logs the error and schedules another refresh rather than permanently stopping live updates. The previously reported abrupt exit did not reproduce in a 100-cycle resize/maximize/reopen stress test; local logging is included to capture further failures.

Windowless launches now write Python errors to `logs/app.log` and native-fault information to `logs/native-crash-PID.log`. These files stay on your computer. If another exit occurs, retain those logs before replacing the app. The old running process must be closed and the updated Start.cmd launched to load this fix.

Run `python -m unittest discover -s tests -v` from this folder. Tests cover naming, recorded-sample selection, missing counters, pin lifetime, comparisons, blur compositing, focus buttons, responsive layout, separate windows, pause and image generation.

For console errors, run `python gpu_live_graphs.py`. For driver availability, run `nvidia-smi`.
