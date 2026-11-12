# Contributing

Keep the four default measurement panels and approved dark visual language. Small changes should preserve existing controls and data semantics.

## Development setup

```powershell
python -m pip install -r requirements.txt
python gpu_live_graphs.py
python -m unittest discover -s tests -v
python tools/check_docs.py
```

Windows component tests open temporary Tk windows. Do not interact with those windows while checks are running. Tests use synthetic records; an NVIDIA GPU is not required for the model/rendering tests. The live app still requires the NVIDIA driver.

## Structure

| File | Responsibility |
| --- | --- |
| `gpu_data.py` | Driver query, immutable readings/snapshots, GPU identity, pins |
| `dashboard.py` | Main/detached windows, view orchestration, interaction |
| `graph_scene.py` | Pillow graph and inspector rendering |
| `chart_view.py` | Zoom/time view and color/style normalization |
| `controls.py` | Dark selectors, quick/export menus, thin scrollbars |
| `window_chrome.py` | Frameless window controls and resize grips |
| `ambient_theme.py` | Low-contrast animated background |
| `diagnostics.py` | Local Python/native-fault logs |
| `exporting.py` | Visible-range CSV and PDF exports |

## Verification

Choose checks appropriate to the change. For window behavior, test actual edge/corner drags, maximize/restore, minimize/taskbar restore, detached-window close, and mixed DPI where available. Programmatic geometry changes alone do not prove mouse resizing.

For data changes, keep measured zero distinct from unavailable values. Pins must reference a real recorded snapshot, and exports must match the selected GPU and visible time range.

## Screenshots

Run `python tools/capture_screenshots.py` on Windows, then inspect every PNG. Keep the DEMO labels and explain synthetic readings in accompanying text. Do not present documentation waveforms as hardware benchmarks.

## Bug reports

Include app version, Windows/Python version, driver version, GPU models, steps, and whether it occurs with detached windows or multiple displays. Review logs for personal paths or other sensitive information before sharing. Do not post raw credentials or unrelated screenshots.

## Pull requests

Describe the user-visible problem, final behavior, checks run, and remaining limitations. Do not mark an unreproduced crash as resolved solely because a short stress test passes.
