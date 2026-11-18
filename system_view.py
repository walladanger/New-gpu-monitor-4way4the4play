"""Three composable CPU/RAM/disk panels using the existing dark visual language."""
from __future__ import annotations

import colorsys
from collections import deque
import tkinter as tk

from graph_scene import BG, PANEL, TEXT, MUTED, GRID, COLORS
from chart_view import LINE_STYLES
from system_graph import MODE_UNITS, available_series, render_system_graph, series_label,sort_series
from ui_resources import PhotoImage
from resource_menu import ResourceMenu,ColorMenu,option


SERIES_MODES={
    "cpu":("cpu_percent","cpu_clock"),
    "ram":("ram_percent","ram_capacity"),
    "disk":("disk_rate","disk_capacity"),
}
MODE_TITLES={
    "cpu_percent":"Logical CPU utilization (%)",
    "cpu_clock":"Reported CPU clock (GHz)",
    "ram_percent":"System RAM utilized (%)",
    "ram_capacity":"System RAM capacity (GiB)",
    "disk_rate":"Physical-disk read/write (MiB/s)",
    "disk_capacity":"Logical volume capacity (GiB)",
}
GROUP_TITLES={"cpu":"CPU · logical processors","ram":"System RAM","disk":"Storage · capacity and I/O"}
PALETTES={"Original","Spectrum"}


def series_color(key, index=0, palette="Original"):
    if palette=="Original" and index<len(COLORS):
        return COLORS[index]
    # Stable hue from sensor identity; no global palette mutation.
    digest=sum((i+1)*ord(c) for i,c in enumerate(key))
    hue=((digest*0.61803398875)%1.0)
    r,g,b=colorsys.hsv_to_rgb(hue,.64,.93)
    return "#{:02X}{:02X}{:02X}".format(round(r*255),round(g*255),round(b*255))


def initial_selection(mode, available):
    keys=set(available)
    if mode=="cpu_percent":
        return {key for key in available if key=="cpu:total" or
                (key.startswith("cpu:thread:") and int(key.rsplit(":",1)[1])<8)}
    if mode=="disk_rate":
        return {key for key in ("disk:total:read","disk:total:write") if key in keys}
    if mode=="disk_capacity":
        first=next((k for k in available if k.startswith("disk:volume:")),None)
        volume=first.rsplit(":",1)[0] if first else None
        return {k for k in available if volume and k.startswith(volume+":")}
    if mode=="ram_capacity":
        return {k for k in ("ram:used","ram:available") if k in keys}
    return set(available)


class SystemPanel(tk.Frame):
    def __init__(self,parent,controller,group):
        super().__init__(parent,bg=PANEL,highlightbackground=GRID,highlightthickness=1)
        self.controller,self.group=controller,group
        self.mode=SERIES_MODES[group][0]
        self.selected=set()
        self._sensor_keys=()
        self._selection_initialized=set()
        self._mode_selections={}
        self._known_series={}
        self.style="Line"
        self.styles={}
        self.colors={}
        self.palette="Original"
        self.history=()
        self.photo=None
        self._disposed=False

        heading=tk.Frame(self,bg=PANEL)
        heading.pack(fill="x",padx=16,pady=(12,4))
        tk.Label(heading,text=GROUP_TITLES[group],bg=PANEL,fg=TEXT,
                 font=("Segoe UI",12,"bold")).pack(side="left")
        buttons=tk.Frame(heading,bg=PANEL)
        buttons.pack(side="right")
        options=dict(bg=GRID,fg=TEXT,activebackground="#36475b",
                     activeforeground=TEXT,relief="flat",cursor="hand2",
                     font=("Segoe UI",9),borderwidth=0,padx=8,pady=4)
        self.appearance_button=tk.Button(buttons,text="◈ Style / color  ▾",
            command=lambda:ResourceMenu(self.appearance_button,"Graph appearance",self.appearance_options),**options)
        self.appearance_button.pack(side="right",padx=(4,0))
        self.sensor_button=tk.Button(buttons,text="≡ Sensors  ▾",
            command=lambda:ResourceMenu(self.sensor_button,"Sensors",self.sensor_options),**options)
        self.sensor_button.pack(side="right")
        self.subtitle=tk.Label(self,text=MODE_TITLES[self.mode],bg=PANEL,fg=MUTED,
                               font=("Segoe UI",9),anchor="w")
        self.subtitle.pack(fill="x",padx=16)
        self.legends=tk.Label(self,text="Waiting for system sensor readings",bg=PANEL,fg=MUTED,
                              font=("Segoe UI",9),anchor="w",wraplength=800,justify="left")
        self.legends.pack(fill="x",padx=16,pady=(5,1))
        self.canvas=tk.Canvas(self,bg=PANEL,height=245,highlightthickness=0)
        self.canvas._ambient_own_surface=True
        self.canvas.pack(fill="both",expand=True,padx=6,pady=(4,8))
        self.image_item=self.canvas.create_image(0,0,anchor="nw")
        self.canvas.bind("<Configure>",lambda _:self.controller.schedule_redraw())

    def set_selected(self,keys):
        self.selected={key for key in keys if key in self._sensor_keys or not self._sensor_keys}
        self.controller.schedule_redraw()

    def preference_state(self):
        return dict(mode=self.mode,selected=sorted(self.selected) if self.mode in self._selection_initialized else None,
                    style=self.style,palette=self.palette,colors=dict(self.colors),styles=dict(self.styles))

    def restore_preferences(self,state):
        self.mode=state['mode']
        self.style=state['style']
        self.palette=state['palette']
        self.colors=dict(state['colors'])
        self.styles=dict(state['styles'])
        if state['selected'] is not None:
            self.selected=set(state['selected'])
            self._selection_initialized.add(self.mode)
        self._sensor_keys=()
        self.subtitle.configure(text=MODE_TITLES[self.mode])

    def set_style(self,style):
        if style not in LINE_STYLES:
            raise ValueError("Unsupported graph style")
        self.style=style
        for key in self.selected:
            self.styles[key]=style
        self.controller.schedule_redraw()

    def set_palette(self,palette):
        if palette not in PALETTES:
            raise ValueError("Unsupported color scheme")
        self.palette=palette
        for index,key in enumerate(self._sensor_keys):
            self.colors[key]=series_color(key,index,palette)
        self.controller.schedule_redraw()

    def set_color(self,key,color):
        from chart_view import normalize_color
        if key not in self._sensor_keys:
            raise ValueError("Unknown sensor")
        self.colors[key]=normalize_color(color)
        self.controller.schedule_redraw()

    def choose_color(self,key):
        self.after_idle(lambda:ColorMenu(self.appearance_button,self.colors.get(key,COLORS[0]),lambda color:self.set_color(key,color)))

    def change_mode(self,mode):
        if mode not in SERIES_MODES[self.group]:
            raise ValueError("Unknown sensor mode")
        self._mode_selections[self.mode]=set(self.selected)
        self.mode=mode
        self.subtitle.configure(text=MODE_TITLES[mode])
        self.selected=set(self._mode_selections.get(mode,()))
        if mode in self._mode_selections:
            self._selection_initialized.add(mode)
        else:
            self._selection_initialized.discard(mode)
        self._sensor_keys=()
        self.accept(self.history)

    def sensor_options(self):
        rows=[option(MODE_TITLES[mode],lambda m=mode:self.change_mode(m),mode==self.mode) for mode in SERIES_MODES[self.group]]
        rows.extend(option("Select "+name,lambda c=count:self.select_preset(c)) for name,count in
                    (("Total / first",1),("First 4",4),("First 8",8),("All",None)))
        rows.append(option("Clear selection",lambda:self.set_selected(())))
        rows.extend(option(series_label(key),lambda k=key:self.toggle_sensor(k,k not in self.selected),key in self.selected) for key in self._sensor_keys)
        return rows

    def toggle_sensor(self,key,active):
        updated=set(self.selected)
        if active:
            updated.add(key)
        else:
            updated.discard(key)
        self.set_selected(updated)

    def select_preset(self,count):
        if count is None:
            chosen=self._sensor_keys
        elif self.group=="cpu" and self.mode=="cpu_percent":
            first=("cpu:total",)
            threads=[k for k in self._sensor_keys if k.startswith("cpu:thread:")]
            chosen=[k for k in first if k in self._sensor_keys]+threads[:count]
        else:
            chosen=self._sensor_keys[:count]
        self.set_selected(chosen)

    def appearance_options(self):
        rows=[option(style,lambda s=style:self.set_style(s),self.style==style) for style in LINE_STYLES]
        rows.extend(option(name,lambda p=name:self.set_palette(p),name==self.palette) for name in ("Original","Spectrum"))
        rows.append(option("Individual trace color…",submenu=lambda:[option(series_label(k),lambda key=k:self.choose_color(key)) for k in self._sensor_keys]))
        return rows

    def accept(self,history):
        self.history=tuple(history)
        previous=self._known_series.get(self.mode)
        discovered=available_series(self.mode,self.history if previous is None else self.history[-2:])
        keys=sort_series(set(previous or ())|set(discovered))
        self._known_series[self.mode]=keys
        if keys!=self._sensor_keys:
            self._sensor_keys=keys
            for i,key in enumerate(keys):
                self.colors.setdefault(key,series_color(key,i,self.palette))
                self.styles.setdefault(key,self.style)
            if self.mode not in self._selection_initialized:
                self.selected=initial_selection(self.mode,keys)
                self._selection_initialized.add(self.mode)
        latest=self.history[-1].values if self.history else {}
        labels=[]
        for key in keys:
            if key not in self.selected:
                continue
            v=latest.get(key)
            value="—" if v is None else f"{v:.2f}".rstrip("0").rstrip(".")
            labels.append(f"{series_label(key)} {value} {MODE_UNITS[self.mode]}")
        summary=" · ".join(labels[:4])
        if len(labels)>4:
            summary+=f"  (+{len(labels)-4} more)"
        self.legends.configure(text=summary or "Select sensors to display")

    def render(self,history,seconds,right):
        self.accept(history)
        if self.history and right-self.history[-1].stamp>4:
            self.legends.configure(text='Waiting for fresh sensor readings; plotted history is retained')
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        if width<100 or height<100:
            return
        selected=tuple(key for key in self._sensor_keys if key in self.selected)
        background=None
        ambient=getattr(self.winfo_toplevel(),"ambient",None)
        if ambient:
            background=ambient.surface(width,height,PANEL,self.canvas)
        args=(self.mode,width,height,self.history,selected,self.colors.copy(),
              self.styles.copy(),right,seconds)
        presentation=(self.mode,selected,tuple((k,self.colors.get(k),self.styles.get(k))
                                              for k in selected),width,height)
        key=(presentation,len(self.history),
             self.history[-1].stamp if self.history else None,
             width,height,round(right,1))
        def apply(picture):
            if self._disposed or not self.winfo_exists():
                return
            self.photo=PhotoImage(picture,master=self.canvas)
            self.canvas.backdrop_image=picture
            self.canvas.itemconfigure(self.image_item,image=self.photo)
        if self.controller.async_render:
            self.controller.queue_frame(self,key,presentation,args,dict(background=background),
                                        apply,draw=render_system_graph)
        else:
            apply(render_system_graph(*args,background=background))

    def close(self):
        self._disposed=True
        if self.controller.render_pipeline:
            self.controller.render_pipeline.discard(self)
