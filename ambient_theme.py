"""Low-contrast horizontal light drift, painted without changing chart data."""
from ui_resources import PhotoImage
import ctypes
from functools import lru_cache
import math
import os
import time
import tkinter as tk

from PIL import Image

BG, PANEL = "#10151d", "#181f2a"
PERIOD = 120.0
HIGHLIGHT = (4, 4, 5)


def shade(base, position, phase):
    rgb = tuple(int(base[i:i+2],16) for i in (1,3,5))
    light = .5-.5*math.cos(math.tau*(position*.72-phase))
    return tuple(min(255, value+round(amount*light)) for value,amount in zip(rgb,HIGHLIGHT))


@lru_cache(maxsize=128)
def strip(width, base, full_width, offset, phase):
    image = Image.new("RGB", (width,1))
    image.putdata([shade(base,(offset+x)/max(1,full_width),phase) for x in range(width)])
    return image


def gradient_image(width, height, base, full_width, offset, phase):
    return strip(max(1,width),base,max(1,full_width),offset,phase).resize((max(1,width),max(1,height)),Image.Resampling.NEAREST)


def animation_allowed():
    if os.name == "nt":
        try:
            enabled = ctypes.c_int()
            if ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0):
                return bool(enabled.value)
        except (AttributeError,OSError):
            pass
    return True


class AmbientTheme:
    def __init__(self, root):
        self.root = root
        self.animated = animation_allowed()
        self.phase = 0.0
        self.background = self.new_canvas(root)
        self.background.place(x=0,y=0,relwidth=1,relheight=1)
        root.tk.call("lower",self.background._w)

    def new_canvas(self, parent):
        canvas = tk.Canvas(parent,bg=BG,highlightthickness=0,borderwidth=0)
        canvas._ambient_backing = True
        canvas._ambient_item = canvas.create_image(0,0,anchor="nw")
        return canvas

    def position(self, widget):
        return widget.winfo_rootx()-self.root.winfo_rootx()

    def color(self, base, widget):
        x = self.position(widget)+widget.winfo_width()/2
        return "#"+"".join(f"{value:02x}" for value in shade(base,x/max(1,self.root.winfo_width()),self.phase))

    def surface(self, width, height, base, widget=None):
        offset = self.position(widget) if widget else 0
        return gradient_image(width,height,base,max(1,self.root.winfo_width()),offset,self.phase)

    def paint_canvas(self, canvas, width, height, base, position_widget):
        key = (width,height,base,self.root.winfo_width(),self.position(position_widget),self.phase)
        if getattr(canvas,"_ambient_key",None) == key:
            return
        image = self.surface(width,height,base,position_widget)
        item = getattr(canvas,"_ambient_item",None)
        if item is None:
            item = canvas.create_image(0,0,anchor="nw",tags="ambient")
            canvas._ambient_item = item
        canvas._ambient_photo = PhotoImage(image,master=canvas)
        canvas.itemconfigure(item,image=canvas._ambient_photo)
        canvas.tag_lower(item)
        canvas.backdrop_image = image
        canvas._ambient_key = key

    def paint(self, now=None):
        if not self.root.winfo_exists() or not self.root.winfo_viewable():
            return
        self.phase = round(((time.monotonic() if now is None else now)/PERIOD)%1*512)/512 if self.animated else .15
        self.paint_canvas(self.background,self.root.winfo_width(),self.root.winfo_height(),BG,self.root)
        for widget in list(self.root.winfo_children()):
            self.paint_widget(widget)

    def paint_widget(self, widget):
        if (getattr(widget,"_ambient_backing",False) or getattr(widget,"_ambient_exempt",False)
                or isinstance(widget,tk.Toplevel)):
            return
        if not widget.winfo_ismapped():
            return
        if not hasattr(widget,"_ambient_base"):
            try:
                base = widget.cget("background")
            except tk.TclError:
                base = None
            widget._ambient_base = base if base in (BG,PANEL) else None
        base = widget._ambient_base
        if base:
            widget.configure(background=self.color(base,widget))
            if isinstance(widget,tk.Frame):
                if not hasattr(widget,"_ambient_canvas"):
                    canvas = self.new_canvas(widget)
                    widget._ambient_canvas = canvas
                    canvas.place(x=0,y=0,relwidth=1,relheight=1)
                    widget.tk.call("lower",canvas._w)
                    drag = getattr(widget,"_window_drag",None)
                    if drag:
                        drag.bind_drag(canvas)
                self.paint_canvas(widget._ambient_canvas,widget.winfo_width(),widget.winfo_height(),base,widget)
            elif isinstance(widget,tk.Canvas):
                if not getattr(widget,"_ambient_own_surface",False) and not hasattr(widget,"draw"):
                    self.paint_canvas(widget,widget.winfo_width(),widget.winfo_height(),base,widget)
        if getattr(widget,"_ambient_redraw",False):
            widget.draw()
        for child in list(widget.winfo_children()):
            self.paint_widget(child)

