"""Compact, configurable resource gauges and a collapsible occupancy heatmap.

All widgets are native Tk and Pillow, matching the existing GPU dashboard.
"""
from __future__ import annotations
import time
import tkinter as tk

from graph_scene import BG, PANEL, TEXT, MUTED, GRID, COLORS
from resource_analytics import (GAUGE_DEFAULTS, GAUGE_STYLES, HEATMAP_DEFAULT,
    HEATMAP_WINDOWS, GaugeSpec, metric_value, available_metrics, gauge_limit,
    render_gauge, render_occupancy)
from system_graph import series_label
from ui_resources import PhotoImage
from resource_menu import ResourceMenu,ColorMenu,option


BUTTON_STYLE=dict(bg=GRID,fg=TEXT,activebackground="#36475B",activeforeground=TEXT,
                  relief="flat",borderwidth=0,cursor="hand2",font=("Segoe UI",9),
                  padx=7,pady=3)


class ResourceGauge(tk.Frame):
    def __init__(self,parent,index,controller):
        super().__init__(parent,bg=PANEL,highlightbackground=GRID,highlightthickness=1)
        self.controller=controller
        self.index=index
        self.spec=GaugeSpec(GAUGE_DEFAULTS[index], "Ring", COLORS[index%len(COLORS)])
        self.history=()
        self.known_keys=()
        self.photo=None
        self.compact=False
        self._last_value=None
        self._last_units=""
        self._last_frame_key=None
        self.title=tk.Label(self,bg=PANEL,fg=MUTED,font=("Segoe UI",9,"bold"),
                            text=series_label(self.spec.metric),anchor="w")
        self.title.pack(fill="x",padx=9,pady=(8,2))
        self.numeric=tk.Label(self,bg=PANEL,fg=TEXT,font=("Segoe UI",15,"bold"),
                              text="—",anchor="center")
        self.canvas=tk.Canvas(self,bg=PANEL,width=155,height=145,highlightthickness=0)
        self.canvas._ambient_own_surface=True
        self.canvas.pack(fill="both",expand=True,padx=8,pady=(1,7))
        self.image_item=self.canvas.create_image(0,0,anchor="nw")
        options=tk.Frame(self,bg=PANEL)
        options.pack(fill="x",padx=8,pady=(0,8))
        self.options=options
        self.metric_button=tk.Button(options,text="Sensor  ▾",command=lambda:ResourceMenu(self.metric_button,"Sensor",self.metric_options),**BUTTON_STYLE)
        self.metric_button.pack(side="left")
        self.style_button=tk.Button(options,text="Style / color  ▾",command=lambda:ResourceMenu(self.style_button,"Gauge appearance",self.style_options),**BUTTON_STYLE)
        self.style_button.pack(side="right")
        self.canvas.bind("<Configure>",lambda _:self.controller.schedule_redraw())

    def metric_options(self):
        return [option(series_label(key),lambda k=key:self.set_metric(k),key==self.spec.metric)
                for key in (self.known_keys or GAUGE_DEFAULTS)]

    def style_options(self):
        rows=[option(style,lambda s=style:self.set_style(s),style==self.spec.style) for style in GAUGE_STYLES]
        rows.extend(option(name,lambda c=color:self.set_color(c)) for name,color in
                    zip(("Mint","Blue","Amber","Violet","Rose","Lime"),COLORS))
        rows.append(option("Custom color…",self.choose_color))
        return rows

    def choose_color(self):
        self.after_idle(lambda:ColorMenu(self.style_button,self.spec.color,self.set_color))

    def set_metric(self,metric):
        if metric not in (self.known_keys or GAUGE_DEFAULTS):
            raise ValueError("Sensor is unavailable")
        self.spec.metric=metric
        self.title.configure(text=series_label(metric))
        self.controller.schedule_redraw()

    def set_style(self,style):
        if style not in GAUGE_STYLES:
            raise ValueError("Unknown gauge style")
        self.spec.style=style
        self.controller.schedule_redraw()

    def set_color(self,color):
        from chart_view import normalize_color
        self.spec.color=normalize_color(color)
        self.controller.schedule_redraw()

    def set_compact(self,compact):
        if compact==self.compact:
            return
        self.compact=compact
        if compact:
            if self.controller.render_pipeline:
                self.controller.render_pipeline.discard(self)
            self.canvas.pack_forget()
            self.options.pack_forget()
            self.numeric.pack(fill='x',padx=7,pady=(1,8))
        else:
            self._last_frame_key=None
            self.numeric.pack_forget()
            self.canvas.pack(fill="both",expand=True,padx=8,pady=(1,7))
            self.options.pack(fill="x",padx=8,pady=(0,8))

    def render(self,history,now):
        self.history=tuple(history)
        keys=available_metrics(self.history[-2:])
        if keys!=self.known_keys:
            self.known_keys=keys
        # An unavailable clock, drive or CPU sensor is shown as unavailable,
        # never replaced silently by a different available metric.
        self.title.configure(text=series_label(self.spec.metric))
        last=self.history[-1] if self.history else None
        if last and now-last.stamp>4:
            last=None
        value,unit=metric_value(self.spec.metric,last)
        if not isinstance(value,(int,float)):
            label="—"
        else:
            label=f"{value:.2f}".rstrip("0").rstrip(".")+f" {unit}"
        self.numeric.configure(text=label)
        if self.compact:
            return
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        if width<60 or height<60:
            return
        limit=gauge_limit(self.spec.metric,self.history[-300:])
        frame_key=(width,height,self.spec.metric,value,limit,label,self.spec.color,self.spec.style)
        if not self.controller.async_render and frame_key==self._last_frame_key:
            return
        args=(width,height,value,limit,label,self.spec.color,self.spec.style)
        presentation=(width,height,self.spec.metric,self.spec.color,self.spec.style)
        def apply(picture):
            if self.compact or self.controller._closed:
                return
            self.photo=PhotoImage(picture,master=self.canvas)
            self._last_frame_key=frame_key
            self.canvas.backdrop_image=picture
            self.canvas.itemconfigure(self.image_item,image=self.photo)
        if self.controller.async_render:
            self.controller.queue_frame(self,frame_key,presentation,args,{},apply,draw=render_gauge)
        else:
            apply(render_gauge(*args))


class ResourceOverview(tk.Frame):
    """Default four-gauge rack immediately below the four GPU line graphs."""
    def __init__(self,parent,controller):
        super().__init__(parent,bg=PANEL,highlightbackground=GRID,highlightthickness=1)
        self.controller=controller
        self.collapsed=False
        self.columns=None
        heading=tk.Frame(self,bg=PANEL)
        heading.pack(fill="x",padx=14,pady=(9,4))
        tk.Label(heading,text="SYSTEM OVERVIEW",bg=PANEL,fg=TEXT,
                 font=("Segoe UI",13,"bold")).pack(side="left")
        self.collapse_button=tk.Button(heading,text="Minimize ▴",command=self.toggle,
                                      **BUTTON_STYLE)
        self.collapse_button.pack(side="right")
        self.grid_content=tk.Frame(self,bg=PANEL)
        self.grid_content.pack(fill="both",expand=True,padx=9,pady=(0,10))
        self.gauges=[ResourceGauge(self.grid_content,i,controller) for i in range(4)]
        self.bind("<Configure>",lambda event:self.arrange(event.width))

    def toggle(self):
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self,collapsed):
        self.collapsed=bool(collapsed)
        self.collapse_button.configure(text="Expand ▾" if self.collapsed else "Minimize ▴")
        for gauge in self.gauges:
            gauge.set_compact(self.collapsed)
        self.arrange(max(1,self.winfo_width()),force=True)
        self.controller.schedule_layout()
        self.controller.schedule_redraw()

    def arrange(self,width,force=False):
        columns=4 if width>=960 else (2 if width>=520 else 1)
        if self.columns==columns and not force:
            return
        self.columns=columns
        for gauge in self.gauges:
            gauge.grid_forget()
        for col in range(4):
            self.grid_content.columnconfigure(col,weight=0)
        for col in range(columns):
            self.grid_content.columnconfigure(col,weight=1,uniform="gauges")
        for i,gauge in enumerate(self.gauges):
            gauge.grid(row=i//columns,column=i%columns,sticky="nsew",padx=4,pady=4)

    def render(self,history,now):
        for gauge in self.gauges:
            gauge.render(history,now)


class OccupancyHeatmapPanel(tk.Frame):
    """Additional analytics accordion; colors encode recorded time in a band."""
    def __init__(self,parent,controller):
        super().__init__(parent,bg=PANEL,highlightbackground=GRID,highlightthickness=1)
        self.controller=controller
        self.expanded=False
        self.metric=HEATMAP_DEFAULT
        self.range_name="5 minutes"
        self.photo=None
        self._known=()
        header=tk.Frame(self,bg=PANEL)
        header.pack(fill="x",padx=14,pady=8)
        self.toggle_button=tk.Button(
            header,text="▸  ADVANCED ANALYTICS · TIME OCCUPANCY HEATMAP",
            command=self.toggle,anchor="w",bg=PANEL,fg=TEXT,activebackground=GRID,
            activeforeground=TEXT,relief="flat",borderwidth=0,font=("Segoe UI",11,"bold"))
        self.toggle_button.pack(side="left",fill="x",expand=True)
        self.body=tk.Frame(self,bg=PANEL)
        controls=tk.Frame(self.body,bg=PANEL)
        controls.pack(fill="x",padx=12,pady=(0,5))
        tk.Label(controls,text="Sensor",fg=MUTED,bg=PANEL).pack(side="left")
        self.sensor_button=tk.Button(controls,text="CPU total  ▾",
            command=lambda:ResourceMenu(self.sensor_button,"Heatmap sensor",self.sensor_options),**BUTTON_STYLE)
        self.sensor_button.pack(side="left",padx=(6,14))
        tk.Label(controls,text="Window",fg=MUTED,bg=PANEL).pack(side="left")
        self.window_button=tk.Button(controls,text=self.range_name+"  ▾",
            command=lambda:ResourceMenu(self.window_button,"Heatmap window",self.window_options),**BUTTON_STYLE)
        self.window_button.pack(side="left",padx=6)
        tk.Label(self.body,text="More recorded time in each cell → yellow, red, then purple. Missing samples and gaps are not counted.",
                 fg=MUTED,bg=PANEL,font=("Segoe UI",9),anchor="w",wraplength=850).pack(
                     fill="x",padx=12,pady=(2,6))
        self.canvas=tk.Canvas(self.body,bg=PANEL,height=285,highlightthickness=0)
        self.canvas._ambient_own_surface=True
        self.canvas.pack(fill="both",expand=True,padx=8,pady=(0,12))
        self.image_item=self.canvas.create_image(0,0,anchor="nw")
        self.canvas.bind("<Configure>",lambda _:self.controller.schedule_redraw())

    def sensor_options(self):
        return [option(series_label(key),lambda k=key:self.set_metric(k),key==self.metric) for key in self._known]

    def window_options(self):
        return [option(name,lambda n=name:self.set_window(n),name==self.range_name) for name in HEATMAP_WINDOWS]

    def toggle(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self,value):
        self.expanded=bool(value)
        if not self.expanded and self.controller.render_pipeline:
            self.controller.render_pipeline.discard(self)
        self.toggle_button.configure(text=("▾" if value else "▸")+
                                     "  ADVANCED ANALYTICS · TIME OCCUPANCY HEATMAP")
        if self.expanded:
            self.body.pack(fill="both",expand=True,padx=8,pady=(0,9))
        else:
            self.body.pack_forget()
        self.controller.schedule_layout()
        self.controller.schedule_redraw()

    def set_metric(self,key):
        if key not in self._known:
            raise ValueError("Unknown resource sensor")
        self.metric=key
        self.sensor_button.configure(text=series_label(key)+"  ▾")
        self.controller.schedule_redraw()

    def set_window(self,name):
        if name not in HEATMAP_WINDOWS:
            raise ValueError("Unknown time range")
        self.range_name=name
        self.window_button.configure(text=name+"  ▾")
        self.controller.schedule_redraw()

    def render(self,history,now):
        if not self.expanded:
            return
        keys=available_metrics(tuple(history)[-2:],self._known)
        if keys!=self._known:
            self._known=keys
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        if width<150 or height<100:
            return
        history=tuple(history)
        args=(width,height,history,self.metric,now,HEATMAP_WINDOWS[self.range_name])
        presentation=(width,height,self.metric,self.range_name)
        key=(presentation,len(history),history[-1].stamp if history else None,round(now,1))
        def apply(picture):
            if not self.expanded or self.controller._closed:
                return
            self.photo=PhotoImage(picture,master=self.canvas)
            self.canvas.backdrop_image=picture
            self.canvas.itemconfigure(self.image_item,image=self.photo)
        if self.controller.async_render:
            self.controller.queue_frame(self,key,presentation,args,{},apply,draw=render_occupancy)
        else:
            apply(render_occupancy(*args))
