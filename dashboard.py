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

from PIL import Image, ImageDraw

from gpu_data import Collector, METRICS, PinStore, Snapshot, panel_columns, gpu_labels
from graph_scene import BG, PANEL, TEXT, MUTED, GRID, COLORS, font, render_graph
from chart_view import TimeView
from controls import DarkSelect, QuickMenu, ExportMenu, SlimScrollbar
from exporting import visible_records, export_csv, export_pdf
from ambient_theme import AmbientTheme
from window_chrome import WindowChrome
from app_paths import user_path, data_directory
from history_store import HistoryStore
from preferences import Preferences
from version import VERSION
from render_pipeline import RenderPipeline
from ui_resources import PhotoImage,BooleanVar,drain_resources
from chart_view import normalize_color, LINE_STYLES

WINDOWS = {"30 seconds":30,"1 minute":60,"2 minutes":120,"5 minutes":300,"10 minutes":600,
           "15 minutes":900,"30 minutes":1800,"45 minutes":2700,"1 hour":3600}


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
    control.icon = PhotoImage(icon, master=parent)
    control.configure(image=control.icon, padx=5, pady=2)
    return control


def clock_button(parent, command):
    icon = Image.new('RGBA',(88,88))
    draw = ImageDraw.Draw(icon)
    draw.ellipse((9,9,79,79),fill='#c9cdd4',outline='#080c12',width=4)
    draw.line((44,24,44,44,59,51),fill='#080c12',width=4)
    for box in ((43,15,45,20),(68,43,73,45),(43,68,45,73),(15,43,20,45)):
        draw.rectangle(box,fill='#080c12')
    control=button(parent,'Switch relative / exact local time',command)
    control.icon=PhotoImage(icon.resize((22,22),Image.Resampling.LANCZOS),master=parent)
    control.configure(image=control.icon,padx=3,pady=2)
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
        self.scene_context = None
        self.series_opacity = {}
        self.time_mode = "relative"
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
        self.clock_button = clock_button(actions, self.toggle_time_mode)
        self.clock_button.pack(side="right", padx=3)
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

    def toggle_time_mode(self):
        self.time_mode = "clock" if self.time_mode == "relative" else "relative"
        logging.getLogger("gpu_live_graphs").info("Time axis metric=%s mode=%s", self.key, self.time_mode)
        self.refresh()

    def pointer(self, event):
        if self.scene:
            cursor = "hand2" if self.scene.over_inspector(event.x, event.y) or self.scene.nearest(event.x, event.y) else ""
            if self.canvas.cget("cursor") != cursor:
                self.canvas.configure(cursor=cursor)

    def left_click(self, event):
        logging.getLogger("gpu_live_graphs").info("Graph click metric=%s x=%s y=%s",self.key,event.x,event.y)
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
            logging.getLogger("gpu_live_graphs").info("Pinned metric=%s gpu=%s timestamp=%.6f",self.key,point.uuid,point.snapshot.wall_time)
            self.canvas.create_oval(point.x-5,point.y-5,point.x+5,point.y+5,outline=TEXT,width=2,tags="pending-pin")
            self.row_offset = 10**9  # Reveal the newly pinned sample and its comparison.
            self.refresh()
        else:
            logging.getLogger('gpu_live_graphs').info('Graph click missed metric=%s',self.key)

    def right_click(self, event):
        if self.scene:
            label = self.scene.pin_at(event.x, event.y)
            if label:
                logging.getLogger('gpu_live_graphs').info('Pin removed metric=%s pin=%s',self.key,label)
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
        target = None if self.focused_uuid == uuid else uuid
        targets = self.controller.all_charts() if self.controller.global_gpu_settings.get() else [self]
        for chart in targets:
            chart.focused_uuid = target
        logging.getLogger('gpu_live_graphs').info('GPU button metric=%s gpu=%s global=%s',self.key,uuid,self.controller.global_gpu_settings.get())
        self.controller.schedule_redraw()
        self.refresh()
        QuickMenu(self, uuid, self.value_labels[uuid])

    def series_color(self, uuid):
        return self.series_colors.get(uuid, self.controller.colors.get(uuid, COLORS[0]))

    def render(self, history, devices, colors, selected, seconds, now, available):
        self.last_context = (history, devices, colors, selected, seconds, now, available)
        self.pins.expire(now, seconds)
        left, right = self.view.bounds(seconds, now)
        self.time_scrollbar.set(*self.view.fractions(seconds))
        self.zoom_reset.configure(text="1×" if self.view.zoom==1 else f"{self.view.zoom:.1f}×")
        colors = {uuid: self.series_colors.get(uuid, color) for uuid, color in colors.items()}
        ids = [uid for uid in devices if selected is None or uid == selected]
        names = gpu_labels(devices)
        self.names = names
        focus = self.focused_uuid if self.focused_uuid in ids else None
        for uid,label in self.value_labels.items():
            if uid not in ids and label.winfo_manager():
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
            configuration=(f'{names[uid]}  {value} {self.unit}',colors[uid] if not focus or focus==uid else MUTED,focus==uid)
            if getattr(self.value_labels[uid],'_value_configuration',None)!=configuration:
                self.value_labels[uid].configure(text=f"{names[uid]}  {value} {self.unit}",
                                             fg=colors[uid] if not focus or focus == uid else MUTED,
                                             activeforeground=colors[uid],
                                             font=("Segoe UI", 11, "bold underline" if focus == uid else "bold"))
                self.value_labels[uid]._value_configuration=configuration
            position=(index//columns,index%columns)
            if getattr(self.value_labels[uid],'_grid_position',None)!=position or not self.value_labels[uid].winfo_manager():
                self.value_labels[uid].grid(row=position[0],column=position[1],sticky='w',padx=(0,20))
                self.value_labels[uid]._grid_position=position
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 100 or height < 100:
            return
        ambient = getattr(self.winfo_toplevel(), "ambient", None)
        background = ambient.surface(width,height,PANEL,self.canvas) if ambient else None
        args = (self.key, width, height, history, devices, colors, selected,
                right-left, right, tuple(self.pins.pins), self.inspector_position,
                self.row_offset, self.active_pin, self.text_scale,
                focus, self.line_styles.copy(), now, background)
        kwargs = dict(opacities=self.series_opacity.copy(), time_mode=self.time_mode)
        presentation = (width,height,selected,tuple(colors.items()),tuple(self.line_styles.items()),
                        tuple(self.series_opacity.items()),self.time_mode,focus,tuple(self.pins.pins),
                        self.inspector_position,self.row_offset,self.active_pin,self.view.zoom,self.view.lag)
        key = (presentation,len(history),history[-1].stamp if history else None,round(right,1))
        context = self.last_context
        def apply(scene):
            self.scene = scene
            self.scene_context = context
            self.rendered_bounds = (left,right)
            self.canvas.backdrop_image = scene.image
            self.photo = PhotoImage(scene.image, master=self.canvas)
            self.canvas.itemconfigure(self.image_item, image=self.photo)
            self.canvas.delete('pending-pin')
        if self.controller.async_render:
            self.controller.queue_frame(self,key,presentation,args,kwargs,apply)
        else:
            apply(render_graph(*args,**kwargs))

    def export_series(self, uuid, kind, directory=None):
        if not self.last_context or not self.rendered_bounds:
            raise ValueError("Wait for the graph to render.")
        history, devices, colors, selected, seconds, now, available = self.scene_context or self.last_context
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
                       self.pins.pins, left, right, now, opacities=self.series_opacity, time_mode=self.time_mode)
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
        self.gpu_choice.bind("<<ComboboxSelected>>", lambda _: controller.filter_changed(self))
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
        self.chart.series_opacity = source.series_opacity.copy()
        self.chart.time_mode = source.time_mode
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
        if self.controller.render_pipeline:
            self.controller.render_pipeline.discard(self.chart)
        self.controller.detached.remove(self)
        if hasattr(self,"chrome"):
            self.chrome.detach()
        self.destroy()


class Dashboard(tk.Tk):
    def __init__(self, collect=True, persist=None, data_dir=None, preferences=None, async_render=None):
        super().__init__()
        self.withdraw()
        self._closed = False
        self.async_render = collect if async_render is None else async_render
        self.render_pipeline = None
        self.render_poll_job = None
        self._last_ambient = 0
        self.ui_stalls = 0
        self.max_ui_delay = 0
        self._heartbeat_at = time.monotonic()
        self.global_gpu_settings = BooleanVar(self, True)
        self.global_colors, self.global_styles, self.global_opacity = {}, {}, {}
        self.title(f"GPU Live Graphs {VERSION}")
        self.geometry("1180x960")
        self.minsize(450, 600)
        self.configure(bg=BG)
        self.history = deque(maxlen=4000)
        persist_enabled=collect if persist is None else persist
        preferences_enabled=collect if preferences is None else preferences
        self.data_dir=Path(data_dir) if data_dir is not None else (data_directory() if persist_enabled or preferences_enabled else None)
        self.preferences=Preferences(self.data_dir/'preferences.json') if preferences_enabled else None
        self.saved_preferences=self.preferences.load() if self.preferences else {}
        self.preference_job=None
        self.preferences_error=('Preferences: '+self.preferences.error) if self.preferences and self.preferences.error else None
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
        self.gpu_choice.bind("<<ComboboxSelected>>", lambda _: self.filter_changed(self))
        tk.Label(filters, text="History", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(16, 8))
        self.window_choice = DarkSelect(filters, state="readonly", values=list(WINDOWS), width=11)
        self.window_choice.set("1 minute")
        self.window_choice.pack(side="left")
        self.window_choice.bind("<<ComboboxSelected>>", lambda _: self.schedule_redraw())
        self.actions = tk.Frame(self.toolbar, bg=BG)
        self.actions.grid(row=0, column=1, sticky="e")
        self.export_button = button(self.actions, "Export", self.open_export)
        self.export_button.pack(side="left", padx=(0, 8))
        self.topmost = BooleanVar(value=False)
        tk.Checkbutton(self.actions, text="Always on top", variable=self.topmost,
                       command=lambda: self.attributes("-topmost", self.topmost.get()), bg=BG, fg=MUTED,
                       selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 10)).pack(side="left", padx=8)
        self.pause_button = button(self.actions, "Pause", self.toggle_pause)
        self.pause_button.pack(side="left")
        self.toolbar.bind("<Configure>", self.layout_toolbar)
        options = tk.Frame(self,bg=BG)
        options.pack(fill="x",padx=24,pady=(0,5))
        tk.Checkbutton(options,text="Global GPU settings",variable=self.global_gpu_settings,command=self.toggle_global_gpu_settings,bg=BG,fg=MUTED,selectcolor=PANEL,activebackground=BG,activeforeground=TEXT,font=("Segoe UI",10)).pack(side="left")
        self.settings_button=button(options,"Settings",self.open_settings)
        self.settings_button.pack(side="right")
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
        if self.saved_preferences:
            self.restore_preferences()
        if self.preferences:
            self.preference_job=self.after(1500,self.periodic_preferences)
        if collect:
            self.tick_job = self.after(100, self.tick)
        self.after(250,self.heartbeat)
        logging.getLogger('gpu_live_graphs').info('phase=dashboard_ready async_render=%s',self.async_render)

    def heartbeat(self):
        drain_resources()
        from diagnostics import pulse
        pulse()
        now=time.monotonic()
        delay=max(0,now-self._heartbeat_at-.25)
        self.max_ui_delay=max(self.max_ui_delay,delay)
        if delay>.1:
            self.ui_stalls+=1
            logging.getLogger('gpu_live_graphs').warning('UI delay %.3fs',delay)
        self._heartbeat_at=now
        if not self._closed:
            self.after(250,self.heartbeat)

    def all_charts(self):
        return self.charts+[window.chart for window in self.detached]

    def sync_global_settings(self):
        for chart in self.all_charts():
            chart.series_colors=dict(self.global_colors)
            chart.line_styles=dict(self.global_styles)
            chart.series_opacity=dict(self.global_opacity)
        self.colors.update(self.global_colors)
        for uid,label in self.legend_labels.items():
            label.configure(fg=self.colors[uid])

    def toggle_global_gpu_settings(self):
        if self.global_gpu_settings.get():
            self.sync_global_settings()
        logging.getLogger('gpu_live_graphs').info('Global GPU settings=%s',self.global_gpu_settings.get())
        self.schedule_redraw()

    def apply_gpu_setting(self,chart,uuid,kind,value):
        if kind=='colors':
            value=normalize_color(value)
            attribute,canonical='series_colors',self.global_colors
        elif kind=='styles':
            if value not in LINE_STYLES:
                raise ValueError('Unknown line style')
            attribute,canonical='line_styles',self.global_styles
        elif kind=='opacity':
            import math
            value=float(value)
            if not math.isfinite(value) or not 0<=value<=1:
                raise ValueError('Opacity must be between zero and one')
            attribute,canonical='series_opacity',self.global_opacity
        else:
            raise ValueError('Unknown GPU setting')
        targets=self.all_charts() if self.global_gpu_settings.get() else [chart]
        if self.global_gpu_settings.get():
            canonical[uuid]=value
            if kind=='colors':
                self.colors[uuid]=value
                if uuid in self.legend_labels:
                    self.legend_labels[uuid].configure(fg=value)
        for target in targets:
            getattr(target,attribute)[uuid]=value
        chart.refresh()
        self.schedule_redraw()

    def queue_frame(self,owner,key,presentation,args,kwargs,apply):
        if self.render_pipeline is None:
            self.render_pipeline=RenderPipeline()
        self.render_pipeline.request(owner,key,presentation,render_graph,args,kwargs,apply)
        if self.render_poll_job is None:
            self.render_poll_job=self.after(16,self.poll_renders)

    def poll_renders(self):
        self.render_poll_job=None
        if self._closed or self.render_pipeline is None:
            return
        drain_resources()
        self.render_pipeline.poll()
        if self.render_pipeline.busy():
            self.render_poll_job=self.after(16,self.poll_renders)

    def wait_for_renders(self,timeout=15):
        deadline=time.monotonic()+timeout
        # Wait for frames requested at entry (or newer), even while live sampling continues.
        targets={owner:state['wanted_id'] for owner,state in self.render_pipeline.states.items()} if self.render_pipeline else {}
        while self.render_pipeline and any(owner in self.render_pipeline.states and self.render_pipeline.states[owner]['done_id']<serial for owner,serial in targets.items()):
            self.update()
            if time.monotonic()>deadline:
                raise TimeoutError('Graph rendering did not finish')
            time.sleep(.005)

    def open_settings(self):
        from settings_menu import SettingsMenu
        return SettingsMenu(self,self.settings_button)

    def selected_uuid(self,control):
        index=control.current()
        return list(self.devices)[index-1] if 0<index<=len(self.devices) else None

    def apply_gpu_selection(self,root):
        uid=getattr(root,'pending_gpu',None)
        if uid in self.devices:
            root.gpu_choice.set(root.gpu_choice.cget('values')[list(self.devices).index(uid)+1])
            root.pending_gpu=None

    def filter_changed(self,root):
        root.pending_gpu=None
        self.schedule_redraw()

    def restore_view(self,chart,state):
        chart.series_colors=dict(state.get('colors',{}))
        chart.line_styles=dict(state.get('styles',{}))
        chart.series_opacity=dict(state.get("opacity",{}))
        chart.time_mode=state.get("time_mode","relative")
        chart.focused_uuid=state.get('focus')
        chart.view.zoom=state.get('zoom',1)
        chart.view.lag=state.get('lag',0)

    def restore_preferences(self):
        state=self.saved_preferences.get('main',{})
        self.global_gpu_settings.set(state.get('global_gpu_settings',True))
        canonical=self.saved_preferences.get('gpu_settings',{})
        self.global_colors=dict(canonical.get('colors',{}))
        self.global_styles=dict(canonical.get('styles',{}))
        self.global_opacity=dict(canonical.get('opacity',{}))
        self.window_choice.set(state.get('history','1 minute'))
        self.pending_gpu=state.get('gpu')
        self.topmost.set(state.get('topmost',False))
        self.attributes('-topmost',self.topmost.get())
        if state.get('bounds'):
            self.chrome.restore_bounds(state['bounds'],state.get('maximized',False))
        for chart in self.charts:
            self.restore_view(chart,state.get('charts',{}).get(chart.key,{}))
        for item in self.saved_preferences.get('detached',[]):
            source=next((c for c in self.charts if c.key==item['metric']),None)
            if source is None:
                continue
            window=self.open_window(source)
            self.restore_view(window.chart,item)
            window.window_choice.set(item.get('history','1 minute'))
            window.pending_gpu=item.get('gpu')
            if item.get('bounds'):
                window.chrome.restore_bounds(item['bounds'],item.get('maximized',False))

        if self.global_gpu_settings.get():
            if not self.global_colors:
                self.global_colors.update(self.charts[0].series_colors)
                self.global_styles.update(self.charts[0].line_styles)
                self.global_opacity.update(self.charts[0].series_opacity)
            self.sync_global_settings()

    def chart_preferences(self,chart):
        colors={uid:chart.series_color(uid) for uid in self.devices}
        colors.update(chart.series_colors)
        return {'colors':colors,'styles':chart.line_styles,'opacity':chart.series_opacity,'time_mode':chart.time_mode,'focus':chart.focused_uuid,
                'zoom':chart.view.zoom,'lag':chart.view.lag}

    def preference_state(self):
        state={'schema':1,'main':{'bounds':list(self.chrome.preference_bounds()),'maximized':self.chrome.is_maximized(),
               'global_gpu_settings':self.global_gpu_settings.get(),'topmost':self.topmost.get(),'gpu':getattr(self,'pending_gpu',None) or self.selected_uuid(self.gpu_choice),
               'history':self.window_choice.get(),'charts':{c.key:self.chart_preferences(c) for c in self.charts}},'detached':[]}
        state['gpu_settings']={'colors':self.global_colors,'styles':self.global_styles,'opacity':self.global_opacity}
        for window in self.detached:
            item=self.chart_preferences(window.chart)
            item.update(metric=window.chart.key,bounds=list(window.chrome.preference_bounds()),maximized=window.chrome.is_maximized(),
                        gpu=getattr(window,'pending_gpu',None) or self.selected_uuid(window.gpu_choice),history=window.window_choice.get())
            state['detached'].append(item)
        return state

    def save_preferences(self):
        if not self.preferences:
            return
        try:
            self.preferences.save(self.preference_state())
            if not self.preferences.read_only:
                self.preferences_error=None
        except (OSError,ValueError,TypeError) as error:
            message='Could not save preferences: '+str(error)
            if message!=self.preferences_error:
                logging.getLogger('gpu_live_graphs').error(message)
            self.preferences_error=message

    def periodic_preferences(self):
        self.preference_job=None
        if not self._closed:
            self.save_preferences()
            self.preference_job=self.after(5000,self.periodic_preferences)

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
        return tuple(self.history), self.devices.copy(), self.colors.copy(), selected, seconds, now, frozenset(available)

    def redraw(self):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = None
        if time.monotonic()-self._last_ambient > 1:
            for root in [self]+self.detached:
                root.ambient.paint()
            self._last_ambient=time.monotonic()
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
        selections={root:self.selected_uuid(root.gpu_choice) for root in [self]+self.detached}
        if error!=self.error:
            logging.getLogger('gpu_live_graphs').info('Driver status: %s',error or 'connected')
        self.error = error
        self.available = {reading.uuid for reading in snapshot.readings}
        self.history.append(snapshot)
        if save and self.store:
            self.store.append(snapshot,error)
        if snapshot.readings:
            self.latest_at, self.latest_wall = snapshot.stamp, snapshot.wall_time
        for reading in snapshot.readings:
            if reading.uuid not in self.colors:
                logging.getLogger('gpu_live_graphs').info('GPU detected name=%s uuid=%s',reading.name,reading.uuid)
                self.colors[reading.uuid] = self.global_colors.get(reading.uuid,COLORS[len(self.colors)%len(COLORS)])
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
        for root in [self]+self.detached:
            root.gpu_choice.configure(values=self.gpu_choice.cget('values'))
            uid=selections[root]
            root.gpu_choice.set(names[uid] if uid in names else 'All GPUs')
            self.apply_gpu_selection(root)
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
            elif kind=='recovered':
                self.storage_error=None

    def export_stored(self,uuid):
        if not self.store:
            raise ValueError('Stored history is not enabled in this demo/test instance.')
        if uuid not in self.devices:
            raise ValueError('Choose a GPU first.')
        destination=self.data_dir/'exports' if self.data_dir else user_path('exports')
        destination.mkdir(parents=True,exist_ok=True)
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
        if self.preferences_error:
            status+=' · '+self.preferences_error
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
        self.save_preferences()
        self._closed = True
        logging.getLogger('gpu_live_graphs').info('Dashboard closing ui_stalls=%s max_ui_delay=%.3fs',self.ui_stalls,self.max_ui_delay)
        if self.render_pipeline:
            self.render_pipeline.close()
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
        drain_resources()


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

