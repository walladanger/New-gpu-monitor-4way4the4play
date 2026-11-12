"""Responsive graphs, detachable windows and pinned driver samples."""
from __future__ import annotations

from collections import deque
from datetime import datetime
import os
from pathlib import Path
import queue
import logging
import sys
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from gpu_data import Collector, METRICS, PinStore, Snapshot, panel_columns, gpu_labels
from graph_scene import BG, PANEL, TEXT, MUTED, GRID, COLORS, font, render_graph
from chart_view import TimeView
from controls import DarkSelect, QuickMenu, ExportMenu, SlimScrollbar
from exporting import visible_records, export_csv, export_pdf
from ambient_theme import AmbientTheme
from window_chrome import WindowChrome
from app_paths import user_path, data_directory
from history_store import HistoryStore
from version import VERSION

WINDOWS = {"1 minute": 60, "5 minutes": 300, "15 minutes": 900, "1 hour": 3600}


def button(parent, text, command):
    return tk.Button(parent, text=text, command=command, bg=PANEL, fg=TEXT,
                     activebackground=GRID, activeforeground=TEXT, relief="flat",
                     padx=12, pady=5, font=("Segoe UI", 9), cursor="hand2")


def popout_button(parent, command):
    icon = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.line((9, 5, 4, 5, 4, 18, 17, 18, 17, 13), fill=MUTED, width=2)
    draw.line((10, 12, 19, 3, 12, 3), fill=TEXT, width=2)
    draw.line((19, 3, 19, 10), fill=TEXT, width=2)
    # Scale the glyph to 75%, retaining the original canvas and comfortable hit area.
    icon = icon.transform(icon.size, Image.Transform.AFFINE,
                          (4/3, 0, -icon.width/6, 0, 4/3, -icon.height/6),
                          resample=Image.Resampling.BICUBIC)
    control = button(parent, "", command)
    control.icon = ImageTk.PhotoImage(icon, master=parent)
    control.configure(image=control.icon, padx=5, pady=2)
    return control


class Chart(tk.Frame):
    def __init__(self, parent, controller, key, title, unit, detachable=True, pins=None):
        super().__init__(parent, bg=PANEL, highlightbackground=GRID, highlightthickness=1)
        self.controller, self.key, self.title, self.unit = controller, key, title, unit
        self.pins = pins if pins is not None else PinStore()
        self.value_labels = {}
        self.scene, self.photo = None, None
        self.inspector_position, self.drag_origin = None, None
        self.row_offset, self.active_pin = 0, None
        self.last_context = None
        self.focused_uuid = None
        self.series_colors, self.line_styles, self.names = {}, {}, {}
        self.view = TimeView()
        self.rendered_bounds = None
        self.text_scale = max(1, min(2, float(self.tk.call("tk", "scaling")) / (96/72)))
        heading = tk.Frame(self, bg=PANEL)
        heading.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(heading, text=title, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        actions = tk.Frame(heading, bg=PANEL)
        actions.pack(side="right")
        if detachable:
            self.popout = popout_button(actions, lambda: controller.open_window(self))
            self.popout.pack(side="right", padx=(6, 0))
        button(actions, "+", lambda: self.zoom_by(1.25)).pack(side="right", padx=1)
        button(actions, "−", lambda: self.zoom_by(1/1.25)).pack(side="right", padx=1)
        self.zoom_reset = button(actions, "1×", self.reset_zoom)
        self.zoom_reset.configure(padx=6)
        self.zoom_reset.pack(side="right", padx=(6, 0))
        tk.Label(heading, text=unit, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="right")
        self.values = tk.Frame(self, bg=PANEL)
        self.values.pack(fill="x", padx=20, pady=(9, 0))
        self.time_scrollbar = SlimScrollbar(self, "horizontal", self.pan_time)
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, height=220)
        self.canvas._ambient_own_surface = True
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Configure>", lambda _: controller.schedule_redraw())
        self.canvas.bind("<Button-1>", self.left_click)
        self.canvas.bind("<Button-3>", self.right_click)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag_origin", None))
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Motion>", self.pointer)

    def pointer(self, event):
        if self.scene:
            cursor = "hand2" if self.scene.nearest(event.x, event.y) or self.scene.over_inspector(event.x, event.y) else ""
            self.canvas.configure(cursor=cursor)

    def left_click(self, event):
        if not self.scene:
            return
        if self.scene.over_inspector(event.x, event.y):
            left, top, _, _ = self.scene.inspector
            if event.y < top + round(55*self.text_scale):
                self.drag_origin = (event.x-left, event.y-top)
            else:
                self.active_pin = self.scene.pin_at(event.x, event.y)
                self.refresh()
            return
        point = self.scene.nearest(event.x, event.y)
        if point:
            pin = self.pins.add(point.snapshot, point.uuid)
            self.active_pin = pin.label
            self.row_offset = 10**9  # Reveal the newly pinned sample and its comparison.
            self.refresh()

    def right_click(self, event):
        if self.scene:
            label = self.scene.pin_at(event.x, event.y)
            if label:
                self.pins.remove(label)
                if self.active_pin == label:
                    self.active_pin = None
                self.refresh()

    def drag(self, event):
        if self.drag_origin:
            dx, dy = self.drag_origin
            self.inspector_position = (event.x-dx, event.y-dy)
            self.refresh()

    def wheel(self, event):
        if self.scene and self.scene.over_inspector(event.x, event.y):
            direction = -1 if event.delta > 0 else 1
            self.row_offset = max(0, min(self.scene.scroll_max, self.scene.scroll_offset+direction*42))
            self.refresh()
            return "break"
        if getattr(event, "state", 0) & 1:
            return self.controller.scroll_graphs(event)
        anchor = (event.x-48)/max(1, self.canvas.winfo_width()-63)
        self.zoom_by(1.2**(event.delta/120), anchor)
        return "break"

    def zoom_by(self, factor, anchor=.5):
        if self.last_context:
            *_, seconds, now, available = self.last_context
            self.view.zoom_by(factor, seconds, now, anchor)
            self.refresh()

    def reset_zoom(self):
        self.view.reset()
        self.refresh()

    def pan_time(self, action, fraction):
        if self.last_context and action == "moveto":
            *_, seconds, now, available = self.last_context
            self.view.pan_to(float(fraction), seconds, now)
            self.refresh()

    def refresh(self):
        if self.last_context:
            self.render(*self.last_context)

    def focus_gpu(self, uuid):
        self.focused_uuid = None if self.focused_uuid == uuid else uuid
        self.refresh()
        root = self.winfo_toplevel()
        popup = getattr(root, "glass_popup", None)
        if popup:
            popup.close()
        if self.focused_uuid:
            QuickMenu(self, uuid, self.value_labels[uuid])

    def series_color(self, uuid):
        return self.series_colors.get(uuid, self.controller.colors.get(uuid, COLORS[0]))

    def render(self, history, devices, colors, selected, seconds, now, available):
        self.last_context = (history, devices, colors, selected, seconds, now, available)
        self.pins.expire(now, seconds)
        left, right = self.view.bounds(seconds, now)
        self.rendered_bounds = (left, right)
        self.time_scrollbar.set(*self.view.fractions(seconds))
        self.zoom_reset.configure(text="1×" if self.view.zoom==1 else f"{self.view.zoom:.1f}×")
        colors = {uuid: self.series_colors.get(uuid, color) for uuid, color in colors.items()}
        ids = [uid for uid in devices if selected is None or uid == selected]
        names = gpu_labels(devices)
        self.names = names
        focus = self.focused_uuid if self.focused_uuid in ids else None
        for label in self.value_labels.values():
            label.grid_forget()
        # Model names need wider cells than numerical driver indexes.
        label_width = max([self.value_labels[uid].winfo_reqwidth()+20 for uid in ids if uid in self.value_labels] + [195])
        columns = max(1, self.values.winfo_width() // label_width)
        for index, uid in enumerate(ids):
            if uid not in self.value_labels:
                self.value_labels[uid] = tk.Button(self.values, bg=PANEL, activebackground=PANEL,
                                                  relief="flat", borderwidth=0, highlightthickness=0,
                                                  padx=0, pady=0, cursor="hand2", anchor="w",
                                                  command=lambda uuid=uid: self.focus_gpu(uuid),
                                                  font=("Segoe UI", 11, "bold"))
            current = getattr(devices[uid], self.key) if uid in available else None
            value = "—" if current is None else f"{current:.1f}"
            self.value_labels[uid].configure(text=f"{names[uid]}  {value} {self.unit}",
                                             fg=colors[uid] if not focus or focus == uid else MUTED,
                                             activeforeground=colors[uid],
                                             font=("Segoe UI", 11, "bold underline" if focus == uid else "bold"))
            self.value_labels[uid].grid(row=index//columns, column=index%columns, sticky="w", padx=(0, 20))
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 100 or height < 100:
            return
        ambient = getattr(self.winfo_toplevel(), "ambient", None)
        background = ambient.surface(width,height,PANEL,self.canvas) if ambient else None
        self.scene = render_graph(self.key, width, height, history, devices, colors, selected,
                                  right-left, right, self.pins.pins, self.inspector_position,
                                  self.row_offset, self.active_pin, self.text_scale,
                                  focus, self.line_styles, now, background)
        self.canvas.backdrop_image = self.scene.image
        self.photo = ImageTk.PhotoImage(self.scene.image, master=self.canvas)
        self.canvas.itemconfigure(self.image_item, image=self.photo)

    def export_series(self, uuid, kind, directory=None):
        if not self.last_context or not self.rendered_bounds:
            raise ValueError("Wait for the graph to render.")
        history, devices, colors, selected, seconds, now, available = self.last_context
        left, right = self.rendered_bounds
        records = visible_records(history, uuid, left, right)
        if not records:
            raise ValueError("No recorded samples in the visible range.")
        destination = Path(directory) if directory else user_path('exports')
        destination.mkdir(exist_ok=True)
        name = self.names[uuid]
        filename = "".join(c if c.isalnum() else "-" for c in name).strip("-")
        path = destination / (datetime.now().strftime("%Y%m%d-%H%M%S-%f")+f"-{filename}-{self.key}.{kind}")
        if kind == "csv":
            export_csv(path, records, uuid, name)
        elif kind == "pdf":
            colors = {uid: self.series_colors.get(uid, color) for uid,color in colors.items()}
            export_pdf(path, records, uuid, self.key, devices, colors, self.line_styles,
                       self.pins.pins, left, right, now)
        else:
            raise ValueError("Choose CSV or PDF.")
        self.controller.notice = (time.monotonic()+20, f"Saved {name} visible samples to {path}")
        self.controller.refresh_status()
        return path

    def export_image(self):
        if not self.scene:
            return None
        image = Image.new("RGB", (self.scene.image.width, self.scene.image.height+74), PANEL)
        draw = ImageDraw.Draw(image)
        draw.text((16, 10), f"{self.title} ({self.unit})", fill=TEXT, font=font(17, True))
        readings = "    ".join(label.cget("text") for label in self.value_labels.values() if label.winfo_manager())
        draw.text((16, 40), readings, fill=MUTED, font=font(12))
        image.paste(self.scene.image, (0, 74))
        return image


class DetachedWindow(tk.Toplevel):
    def __init__(self, controller, source):
        super().__init__(controller)
        self.withdraw()
        self._closed = False
        self.controller = controller
        self.title(f"{source.title} — GPU Live Graphs")
        self.configure(bg=BG)
        self.geometry("800x540")
        self.minsize(480, 420)
        self.protocol("WM_DELETE_WINDOW", self.close)
        header = tk.Frame(self,bg=BG)
        header.pack(fill="x",padx=16,pady=(10,0))
        title = tk.Label(header,text="GPU Live Graphs",bg=BG,fg=TEXT,font=("Segoe UI",12,"bold"))
        title.pack(side="left")
        self.chrome = WindowChrome(self,header,(title,))
        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", padx=16, pady=12)
        self.gpu_choice = DarkSelect(controls, state="readonly", width=23,
                                     values=controller.gpu_choice.cget("values"))
        self.gpu_choice.set(controller.gpu_choice.get())
        self.gpu_choice.pack(side="left")
        self.gpu_choice.bind("<<ComboboxSelected>>", lambda _: controller.schedule_redraw())
        self.window_choice = DarkSelect(controls, state="readonly", values=list(WINDOWS), width=11)
        self.window_choice.set(controller.window_choice.get())
        self.window_choice.pack(side="left", padx=10)
        self.window_choice.bind("<<ComboboxSelected>>", lambda _: controller.schedule_redraw())
        self.export_button = button(controls, "Export", lambda: controller.open_export([self.chart], self.export_button))
        self.export_button.pack(side="right")
        self.chart = Chart(self, controller, source.key, source.title, source.unit, False, source.pins.copy())
        self.chart.focused_uuid = source.focused_uuid
        self.chart.series_colors = source.series_colors.copy()
        self.chart.line_styles = source.line_styles.copy()
        self.chart.view = TimeView(source.view.zoom, source.view.lag)
        self.chart.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tk.Label(self, text="Shared live data · independent GPU, history and pins · left-click a line to pin",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(fill="x", padx=16, pady=(0, 12))
        self.ambient = AmbientTheme(self)
        self.deiconify()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if getattr(self, "glass_popup", None):
            self.glass_popup.close()
        self.controller.detached.remove(self)
        if hasattr(self,"chrome"):
            self.chrome.detach()
        self.destroy()


class Dashboard(tk.Tk):
    def __init__(self, collect=True, persist=None, data_dir=None):
        super().__init__()
        self.withdraw()
        self._closed = False
        self.title(f"GPU Live Graphs {VERSION}")
        self.geometry("1180x960")
        self.minsize(450, 600)
        self.configure(bg=BG)
        self.history = deque(maxlen=4000)
        persist_enabled=collect if persist is None else persist
        self.data_dir=Path(data_dir) if data_dir is not None else (data_directory() if persist_enabled else None)
        self.store=HistoryStore(self.data_dir/'history.sqlite3') if persist_enabled else None
        self.storage_error=None
        self.restored_count=0
        self.devices, self.colors, self.available = {}, {}, set()
        self.paused, self.frozen_at, self.latest_at = False, None, None
        self.latest_wall, self.error, self.notice = None, None, None
        self.detached = []
        self.redraw_job, self.layout_job, self.tick_job = None, None, None
        self.columns = None
        self.collector = Collector() if collect else None
        self.protocol("WM_DELETE_WINDOW", self.close)
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 6))
        title = tk.Label(header, text="GPU Live Graphs", bg=BG, fg=TEXT, font=("Segoe UI", 21, "bold"))
        title.pack(side="left")
        self.chrome = WindowChrome(self,header,(title,))
        self.live = tk.Label(header, text="CONNECTING", bg=BG, fg=COLORS[0], font=("Segoe UI", 10, "bold"))
        self.live.pack(side="right",padx=(0,10))
        self.chrome.bind_drag(self.live)
        self.subtitle = tk.Label(self, text="NVIDIA driver readings · 1-second refresh · one line per GPU", bg=BG,
                                 fg=MUTED, font=("Segoe UI", 10), wraplength=400, justify="left")
        self.subtitle.pack(anchor="w", padx=25)
        self.toolbar = tk.Frame(self, bg=BG)
        self.toolbar.pack(fill="x", padx=24, pady=(14, 8))
        filters = tk.Frame(self.toolbar, bg=BG)
        filters.grid(row=0, column=0, sticky="w")
        self.toolbar.columnconfigure(0, weight=1)
        tk.Label(filters, text="Show", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        self.gpu_choice = DarkSelect(filters, state="readonly", values=["All GPUs"], width=28)
        self.gpu_choice.set("All GPUs")
        self.gpu_choice.pack(side="left")
        self.gpu_choice.bind("<<ComboboxSelected>>", lambda _: self.schedule_redraw())
        tk.Label(filters, text="History", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(16, 8))
        self.window_choice = DarkSelect(filters, state="readonly", values=list(WINDOWS), width=11)
        self.window_choice.set("1 minute")
        self.window_choice.pack(side="left")
        self.window_choice.bind("<<ComboboxSelected>>", lambda _: self.schedule_redraw())
        self.actions = tk.Frame(self.toolbar, bg=BG)
        self.actions.grid(row=0, column=1, sticky="e")
        self.export_button = button(self.actions, "Export", self.open_export)
        self.export_button.pack(side="left", padx=(0, 8))
        self.topmost = tk.BooleanVar(value=False)
        tk.Checkbutton(self.actions, text="Always on top", variable=self.topmost,
                       command=lambda: self.attributes("-topmost", self.topmost.get()), bg=BG, fg=MUTED,
                       selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 10)).pack(side="left", padx=8)
        self.pause_button = button(self.actions, "Pause", self.toggle_pause)
        self.pause_button.pack(side="left")
        self.toolbar.bind("<Configure>", self.layout_toolbar)
        self.legend = tk.Frame(self, bg=BG)
        self.legend.pack(fill="x", padx=24, pady=(0, 7))
        self.legend_labels = {}
        self.legend.bind("<Configure>", lambda _: self.layout_legend())
        self.instructions = tk.Label(self, text="Click a GPU name for quick options · wheel to zoom · Shift+wheel to scroll the page · click a line to pin",
                                     bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=410, justify="left")
        self.instructions.pack(anchor="w", padx=25, pady=(0, 6))
        self.status = tk.Label(self, text="Reading graphics cards…", bg=BG, fg=MUTED,
                               anchor="w", font=("Segoe UI", 9), wraplength=1100, justify="left")
        self.status.pack(side="bottom", fill="x", padx=24, pady=(8, 12))
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=(18, 8))
        self.viewport = tk.Canvas(body, bg=BG, highlightthickness=0)
        scrollbar = SlimScrollbar(body, "vertical", self.viewport.yview)
        self.page_scrollbar = scrollbar
        self.viewport.pack(side="left", fill="both", expand=True)
        self.viewport.configure(yscrollcommand=scrollbar.set, yscrollincrement=24)
        self.grid_frame = tk.Frame(self.viewport, bg=BG)
        self.grid_item = self.viewport.create_window(0, 0, window=self.grid_frame, anchor="nw")
        self.charts = [Chart(self.grid_frame, self, *metric) for metric in METRICS]
        self.viewport.bind("<Configure>", self.schedule_layout)
        self.viewport.bind("<MouseWheel>", self.scroll_graphs)
        self.ambient = AmbientTheme(self)
        self.deiconify()
        if collect:
            self.tick_job = self.after(100, self.tick)

    def layout_toolbar(self, event):
        narrow = event.width < 850
        self.actions.grid(row=1 if narrow else 0, column=0 if narrow else 1,
                          sticky="w" if narrow else "e", pady=(8, 0) if narrow else 0)
        self.gpu_choice.configure(width=17 if event.width < 600 else 28)

    def layout_legend(self):
        columns = max(1, self.legend.winfo_width() // 180)
        for index, label in enumerate(self.legend_labels.values()):
            label.grid(row=index//columns, column=index%columns, sticky="w", padx=(0, 22), pady=2)

    def schedule_layout(self, _=None):
        if self.layout_job:
            self.after_cancel(self.layout_job)
        self.layout_job = self.after(50, self.layout_graphs)

    def layout_graphs(self):
        self.layout_job = None
        width, height = self.viewport.winfo_width(), self.viewport.winfo_height()
        columns = panel_columns(width)
        rows = 4//columns
        if columns != self.columns:
            for i in range(4):
                self.grid_frame.rowconfigure(i, weight=0, minsize=0, uniform="")
            for i in range(2):
                self.grid_frame.columnconfigure(i, weight=0, minsize=0, uniform="")
            for i in range(columns):
                self.grid_frame.columnconfigure(i, weight=1, uniform="panels")
            for i in range(rows):
                self.grid_frame.rowconfigure(i, weight=1, uniform="panels")
            for i, chart in enumerate(self.charts):
                chart.grid(row=i//columns, column=i%columns, sticky="nsew", padx=6, pady=6)
            self.columns = columns
        content_height = max(height, rows*(300 if columns == 2 else 340))
        self.viewport.itemconfigure(self.grid_item, width=width, height=content_height)
        self.viewport.configure(scrollregion=(0, 0, width, content_height))
        self.status.configure(wraplength=max(350, self.winfo_width()-48))
        self.subtitle.configure(wraplength=max(350, self.winfo_width()-48))
        self.instructions.configure(wraplength=max(350, self.winfo_width()-48))
        self.schedule_redraw()

    def scroll_graphs(self, event):
        if event.widget.winfo_toplevel() == self:
            self.viewport.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"

    def schedule_redraw(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = self.after(60, self.redraw)

    def context(self, gpu_choice, window_choice):
        chosen = gpu_choice.current()
        selected = list(self.devices)[chosen-1] if 0 < chosen <= len(self.devices) else None
        seconds = WINDOWS[window_choice.get()]
        now = self.frozen_at if self.paused else time.monotonic()
        available = self.available if self.paused or (self.latest_at and now-self.latest_at < 3) else set()
        return self.history, self.devices, self.colors, selected, seconds, now, available

    def redraw(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = None
        for root in [self]+self.detached:
            root.ambient.paint()
        context = self.context(self.gpu_choice, self.window_choice)
        if self.winfo_viewable():
            for chart in self.charts:
                chart.render(*context)
        for window in self.detached:
            window.gpu_choice.configure(values=self.gpu_choice.cget("values"))
            if window.winfo_viewable():
                window.chart.render(*self.context(window.gpu_choice, window.window_choice))
        for root in [self]+self.detached:
            if getattr(root, "glass_popup", None):
                root.glass_popup.render()

    def open_window(self, chart):
        window = DetachedWindow(self, chart)
        self.detached.append(window)
        self.schedule_redraw()
        return window

    def open_export(self, charts=None, source=None):
        return ExportMenu(self, charts or self.charts, source or self.export_button)

    def focus_all(self, uuid):
        target = None if all(chart.focused_uuid == uuid for chart in self.charts) else uuid
        for chart in self.charts:
            chart.focused_uuid = target
        self.redraw()

    def toggle_pause(self):
        self.paused = not self.paused
        self.frozen_at = time.monotonic() if self.paused else None
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        self.refresh_status()
        self.redraw()

    def accept(self, snapshot, error=None, save=True):
        self.error = error
        self.available = {reading.uuid for reading in snapshot.readings}
        self.history.append(snapshot)
        if save and self.store:
            self.store.append(snapshot,error)
        if snapshot.readings:
            self.latest_at, self.latest_wall = snapshot.stamp, snapshot.wall_time
        for reading in snapshot.readings:
            if reading.uuid not in self.colors:
                self.colors[reading.uuid] = COLORS[len(self.colors)%len(COLORS)]
                self.legend_labels[reading.uuid] = tk.Button(self.legend, bg=BG, fg=self.colors[reading.uuid],
                                                             activebackground=BG, activeforeground=TEXT,
                                                             font=("Segoe UI", 10), cursor="hand2", relief="flat",
                                                             borderwidth=0, highlightthickness=0, padx=0, pady=0,
                                                             command=lambda uuid=reading.uuid: self.focus_all(uuid))
            self.devices[reading.uuid] = reading
        names = gpu_labels(self.devices)
        for uid, label in self.legend_labels.items():
            label.configure(text=f"● {names[uid]}")
        self.gpu_choice.configure(values=["All GPUs"] + list(names.values()))
        self.layout_legend()

    def poll_history(self):
        if not self.store:
            return
        while True:
            try:
                kind,value=self.store.messages.get_nowait()
            except queue.Empty:
                break
            if kind=='loaded':
                # Restore old records without presenting their values as live.
                current=list(self.history)
                combined=sorted(value+current,key=lambda s:s.stamp)
                available=self.available.copy()
                latest_at,latest_wall,error=self.latest_at,self.latest_wall,self.error
                self.history.clear()
                latest={r.uuid:r for s in value for r in s.readings}
                if latest:
                    self.accept(Snapshot(0,0,tuple(latest.values())),save=False)
                self.history.clear()
                self.history.extend(combined)
                self.available=available
                self.latest_at,self.latest_wall,self.error=latest_at,latest_wall,error
                # Live readings win over restored metadata if the driver was faster.
                for snapshot in current:
                    for reading in snapshot.readings:
                        self.devices[reading.uuid]=reading
                self.restored_count=len(value)
            elif kind=='exported':
                self.notice=(time.monotonic()+20,'Saved stored history to '+value)
            elif kind=='error':
                self.storage_error=value

    def export_stored(self,uuid):
        if not self.store:
            raise ValueError('Stored history is not enabled in this demo/test instance.')
        if uuid not in self.devices:
            raise ValueError('Choose a GPU first.')
        destination=user_path('exports')
        path=destination/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-saved-history.csv')
        self.store.export(path,uuid,gpu_labels(self.devices)[uuid])
        self.notice=(time.monotonic()+20,'Exporting retained history in the background...')
        self.refresh_status()
        return path

    def refresh_status(self):
        stale = self.latest_at is not None and time.monotonic()-self.latest_at >= 3
        state = "PAUSED" if self.paused else "NO DATA" if self.error else "RECONNECTING" if stale else "LIVE" if self.latest_at else "CONNECTING"
        self.live.configure(text=state, fg=COLORS[2] if self.paused or self.error or stale else COLORS[0])
        if self.notice and time.monotonic() < self.notice[0]:
            status = self.notice[1]
        elif self.paused:
            status = "Paused · graphs and pins are frozen. Resume to continue; the pause appears as a gap."
        elif self.error:
            status = self.error + " · Retrying automatically."
        elif stale:
            status = "Waiting for the NVIDIA driver. Old values are hidden until fresh readings arrive."
        else:
            stamp = datetime.fromtimestamp(self.latest_wall).strftime("%H:%M:%S") if self.latest_wall else "—"
            status = f"{len(self.available)} GPU(s) connected · Last update {stamp} · Up to 1 hour in graphs · 24 hours saved on disk (128 MB cap)."
        if self.storage_error or (self.store and self.store.error):
            status+=' · '+(self.storage_error or self.store.error)
        self.status.configure(text=status)

    def tick(self):
        self.tick_job = None
        try:
            self.poll_history()
            while True:
                try:
                    snapshot, error = self.collector.messages.get_nowait()
                except queue.Empty:
                    break
                if not self.paused:
                    self.accept(snapshot, error)
            self.refresh_status()
            self.redraw()
        except Exception:
            self.report_callback_exception(*sys.exc_info())
        finally:
            if not self._closed:
                self.tick_job = self.after(500,self.tick)

    def report_callback_exception(self,exc_type,value,traceback):
        logging.getLogger('gpu_live_graphs').error('UI callback failed',exc_info=(exc_type,value,traceback))
        self.notice = (time.monotonic()+20,'A display error was logged; the dashboard will retry.')
        if hasattr(self,'status') and not self._closed:
            self.refresh_status()

    def save_images(self, charts, directory=None):
        images = [chart.export_image() for chart in charts]
        images = [image for image in images if image is not None]
        if not images:
            self.notice = (time.monotonic()+10, "Wait for the graph to render before saving.")
        else:
            columns = self.columns if len(images) == 4 else 1
            cell_width = max(image.width for image in images)
            cell_height = max(image.height for image in images)
            rows = (len(images)+columns-1)//columns
            output = Image.new("RGB", (columns*cell_width+(columns+1)*12, rows*cell_height+(rows+1)*12), BG)
            for index, image in enumerate(images):
                output.paste(image, (12+(index%columns)*(cell_width+12), 12+(index//columns)*(cell_height+12)))
            try:
                destination = Path(directory) if directory else user_path('captures')
                destination.mkdir(exist_ok=True)
                path = destination / (datetime.now().strftime("GPU-Graphs-%Y%m%d-%H%M%S-%f") + ".png")
                output.save(path)
                self.notice = (time.monotonic()+20, f"Saved graphs and pin details to {path}")
            except OSError as error:
                self.notice = (time.monotonic()+20, f"Could not save the image: {error}")
        self.refresh_status()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if getattr(self, "glass_popup", None):
            self.glass_popup.close()
        if self.collector:
            self.collector.stop.set()
        if self.store:
            self.store.close()
        for window in self.detached:
            window._closed = True
            if hasattr(window,"chrome"):
                window.chrome.detach()
        if hasattr(self,"chrome"):
            self.chrome.detach()
        for job in self.tk.call("after", "info"):
            self.after_cancel(job)
        self.destroy()


def main():
    from diagnostics import configure_logging
    configure_logging()
    logging.getLogger('gpu_live_graphs').info('Application version %s',VERSION)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    if '--self-test' in sys.argv:
        from self_test import run
        index=sys.argv.index('--self-test')
        raise SystemExit(run(Path(sys.argv[index+1])))
    Dashboard().mainloop()
