"""Dark selectors, slim scrollbars and frosted menus painted from app content."""
import colorsys
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from chart_view import LINE_STYLES, normalize_color
from graph_scene import BG, PANEL, TEXT, MUTED, GRID, font, shade_area, dashed_series


def backdrop(root, x, y, width, height):
    """Paint our own widgets/graph images; never capture the desktop."""
    output = Image.new("RGB", (width, height), BG)
    origin = (root.winfo_rootx()+x, root.winfo_rooty()+y)

    def visit(widget, clip):
        if not widget.winfo_ismapped() or isinstance(widget, GlassOverlay):
            return
        left, top = widget.winfo_rootx()-origin[0], widget.winfo_rooty()-origin[1]
        right, bottom = left+widget.winfo_width(), top+widget.winfo_height()
        box = (max(left, clip[0]), max(top, clip[1]), min(right, clip[2]), min(bottom, clip[3]))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        layer = Image.new("RGB", (max(1, right-left), max(1, bottom-top)), PANEL)
        draw = ImageDraw.Draw(layer)
        try:
            layer.paste(widget.cget("background"), (0, 0, layer.width, layer.height))
        except tk.TclError:
            pass
        raster = getattr(widget, "backdrop_image", None)
        if raster is not None:
            layer.paste(raster, (0, 0))
        elif isinstance(widget, (tk.Label, tk.Button, tk.Checkbutton)):
            try:
                text = widget.cget("text")
                face = tkfont.Font(root=root, font=widget.cget("font"))
                size = max(9, face.metrics("linespace")-3)
                anchor = "lm" if widget.cget("anchor") in ("w", "nw", "sw") else "mm"
                pos = (4, layer.height/2) if anchor == "lm" else (layer.width/2, layer.height/2)
                draw.text(pos, text, fill=widget.cget("foreground"), font=font(size, face.actual("weight")=="bold"), anchor=anchor)
            except (tk.TclError, ValueError):
                pass
        output.paste(layer.crop((box[0]-left, box[1]-top, box[2]-left, box[3]-top)), box[:2])
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                visit(child, box)

    for child in root.winfo_children():
        if not isinstance(child, tk.Toplevel):
            visit(child, (0, 0, width, height))
    return output


class GlassOverlay(tk.Canvas):
    def __init__(self, root, source, width, height, on_close=None):
        old = getattr(root, "glass_popup", None)
        if old:
            old.close()
        super().__init__(root, background=BG, highlightthickness=0, takefocus=True, cursor="arrow")
        self._ambient_exempt = True
        self.root, self.source, self.on_close = root, source, on_close
        self.closed = False
        self.width = min(width, max(200, root.winfo_width()-16))
        self.height = min(height, max(160, root.winfo_height()-16))
        self.x = min(max(8, source.winfo_rootx()-root.winfo_rootx()), root.winfo_width()-self.width-8)
        below = source.winfo_rooty()-root.winfo_rooty()+source.winfo_height()+6
        self.y = below if below+self.height < root.winfo_height()-8 else max(8, below-source.winfo_height()-self.height-12)
        self.configure(width=self.width, height=self.height)
        self.item = self.create_image(0, 0, anchor="nw")
        self.place(x=self.x, y=self.y, width=self.width, height=self.height)
        self.tk.call("raise", self._w)
        root.glass_popup = self
        self.outside_binding = root.bind("<Button-1>", self.outside, add="+")
        self.escape_binding = root.bind("<Escape>", lambda _: self.close(), add="+")
        self.bind("<MouseWheel>", lambda _: "break")

    def outside(self, event):
        widget = event.widget
        while widget is not None:
            if widget in (self, self.source):
                return
            widget = getattr(widget, "master", None)
        self.close()

    def render(self):
        if self.closed:
            return
        original = backdrop(self.root, self.x, self.y, self.width, self.height)
        blurred = original.filter(ImageFilter.GaussianBlur(12)).convert("RGBA")
        glass = Image.alpha_composite(blurred, Image.new("RGBA", blurred.size, (8, 12, 19, 198))).convert("RGB")
        mask = Image.new("L", glass.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, self.width-1, self.height-1), radius=12, fill=255)
        original.paste(glass, (0, 0), mask)
        draw = ImageDraw.Draw(original)
        draw.rounded_rectangle((0, 0, self.width-1, self.height-1), radius=12, outline="#49566a")
        self.surface = original
        self.paint(draw)
        self.photo = ImageTk.PhotoImage(original, master=self)
        self.itemconfigure(self.item, image=self.photo)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if getattr(self.root, "glass_popup", None) is self:
            self.root.glass_popup = None
        self.root.unbind("<Button-1>", self.outside_binding)
        self.root.unbind("<Escape>", self.escape_binding)
        if self.on_close:
            self.on_close()
        self.destroy()


class SelectMenu(GlassOverlay):
    def __init__(self, control):
        self.control = control
        self.hover = max(0, control.current())
        super().__init__(control.winfo_toplevel(), control.canvas, max(180, control.winfo_width()), 12+34*len(control.values))
        self.bind("<Button-1>", self.click)
        self.bind("<Motion>", self.move)
        self.bind("<Up>", lambda _: self.navigate(-1))
        self.bind("<Down>", lambda _: self.navigate(1))
        self.bind("<Return>", lambda _: self.choose(self.hover))
        self.focus_set()
        self.render()

    def paint(self, draw):
        for index, value in enumerate(self.control.values):
            top = 6+index*34
            if index == self.hover:
                draw.rounded_rectangle((6, top, self.width-6, top+32), radius=6, fill="#253145")
            draw.text((16, top+16), value, fill=TEXT if index==self.hover else MUTED, font=font(13), anchor="lm")
            if index == self.control.current():
                draw.ellipse((self.width-22, top+13, self.width-16, top+19), fill="#56d6be")

    def navigate(self, direction):
        self.hover = (self.hover+direction)%len(self.control.values)
        self.render()

    def move(self, event):
        index = min(max(0, (event.y-6)//34), len(self.control.values)-1)
        if index != self.hover:
            self.hover = index
            self.render()

    def click(self, event):
        index = (event.y-6)//34
        if 0 <= index < len(self.control.values):
            self.choose(index)

    def choose(self, index):
        value = self.control.values[index]
        self.close()
        self.control.set(value)
        self.control.event_generate("<<ComboboxSelected>>")


class DarkSelect(tk.Frame):
    def __init__(self, parent, values=(), width=20, state=None):
        super().__init__(parent, bg=BG)
        self._ambient_redraw = True
        self.values = tuple(values)
        self.value = self.values[0] if self.values else ""
        self.canvas = tk.Canvas(self, width=width*7+28, height=31, bg=BG, highlightthickness=0, takefocus=True, cursor="hand2")
        self.canvas._ambient_own_surface = True
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        self.canvas.bind("<Button-1>", lambda _: SelectMenu(self))
        self.canvas.bind("<Return>", lambda _: SelectMenu(self))
        self.canvas.bind("<space>", lambda _: SelectMenu(self))
        self.photo = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.draw()

    def current(self):
        return self.values.index(self.value) if self.value in self.values else -1

    def cget(self, key):
        return self.values if key == "values" else super().cget(key)

    def configure(self, cnf=None, **kwargs):
        if "values" in kwargs:
            self.values = tuple(kwargs.pop("values"))
        if "width" in kwargs and hasattr(self, "canvas"):
            self.canvas.configure(width=kwargs.pop("width")*7+28)
        if cnf or kwargs:
            super().configure(cnf, **kwargs)
        if hasattr(self, "canvas"):
            self.draw()

    def draw(self):
        width = max(60, self.canvas.winfo_width() if self.canvas.winfo_width()>1 else int(self.canvas.cget("width")))
        height = max(28, self.canvas.winfo_height())
        ambient = getattr(self.winfo_toplevel(),"ambient",None)
        image = ambient.surface(width,height,BG,self.canvas) if ambient else Image.new("RGB",(width,height),BG)
        draw = ImageDraw.Draw(image)
        fill = ambient.color(PANEL,self.canvas) if ambient else PANEL
        draw.rounded_rectangle((0, 0, width-1, height-1), radius=7, fill=fill, outline=GRID)
        value = self.value
        face = font(13)
        while len(value)>1 and draw.textlength(value, font=face) > width-38:
            value = value[:-2]+"…" if not value.endswith("…") else value[:-2]+"…"
        draw.text((11, height/2), value, fill=TEXT, font=face, anchor="lm")
        draw.line((width-23, height/2-2, width-18, height/2+3, width-13, height/2-2), fill=MUTED, width=2)
        self.canvas.backdrop_image = image
        self.photo = ImageTk.PhotoImage(image, master=self.canvas)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)


class QuickMenu(GlassOverlay):
    def __init__(self, chart, uuid, source):
        self.chart, self.uuid, self.status, self.sliding = chart, uuid, "", False
        self.style_tiles = {}
        super().__init__(chart.winfo_toplevel(), source, 350, 304)
        self.hex_value = tk.StringVar(self, value=chart.series_color(uuid).upper())
        self.hex_entry = tk.Entry(self, textvariable=self.hex_value, width=9, justify="center",
                                  bg=PANEL, fg=chart.series_color(uuid), insertbackground=TEXT,
                                  selectbackground="#30465d", selectforeground=TEXT,
                                  relief="flat", highlightthickness=1, highlightbackground=GRID,
                                  highlightcolor=chart.series_color(uuid), font=("Segoe UI", 10))
        self.create_window(self.width-76, 71, window=self.hex_entry, width=118, height=27)
        self.hex_trace = self.hex_value.trace_add("write", self.preview_hex)
        self.hex_entry.bind("<Return>", lambda _: self.apply_hex())
        self.hex_entry.bind("<FocusOut>", lambda _: self.apply_hex())
        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.motion)
        self.bind("<ButtonRelease-1>", lambda _: setattr(self, "sliding", False))
        self.render()

    def preview_hex(self, *_):
        if self.closed:
            return
        try:
            color = normalize_color(self.hex_value.get())
        except ValueError:
            return  # Partial input is expected while typing; keep the last valid color.
        if color != self.chart.series_color(self.uuid).upper():
            self.chart.series_colors[self.uuid] = color
            self.status = ""
            self.chart.refresh()
        self.hex_entry.configure(highlightbackground=GRID)
        self.render()

    def close(self):
        if not self.closed and hasattr(self, "hex_trace"):
            self.hex_value.trace_remove("write", self.hex_trace)
        super().close()

    def apply_hex(self):
        if self.closed:
            return "break"
        try:
            color = normalize_color(self.hex_value.get())
        except ValueError as error:
            self.status = str(error)
            self.hex_entry.configure(highlightbackground="#ff8792", highlightcolor="#ff8792")
            self.render()
            return "break"
        self.status = ""
        self.hex_value.set(color)
        self.hex_entry.configure(highlightcolor=color)
        return "break"

    def paint(self, draw):
        color = self.chart.series_color(self.uuid)
        draw.text((16, 19), self.chart.names.get(self.uuid, "GPU"), fill=color, font=font(15, True), anchor="lm")
        draw.text((self.width-20, 19), "×", fill=MUTED, font=font(19), anchor="mm")
        draw.text((16, 43), self.chart.title+" · this graph only", fill=MUTED, font=font(12), anchor="lm")
        draw.text((16, 71), "Color", fill=TEXT, font=font(12), anchor="lm")
        if hasattr(self, "hex_entry"):
            self.hex_entry.configure(fg=color, insertbackground=TEXT)
        for x in range(16, self.width-16):
            rgb = tuple(round(v*255) for v in colorsys.hsv_to_rgb((x-16)/(self.width-32), .72, .95))
            draw.line((x, 90, x, 102), fill=rgb)
        rgb = tuple(int(color[i:i+2], 16)/255 for i in (1,3,5))
        hue = colorsys.rgb_to_hsv(*rgb)[0]
        x = 16+hue*(self.width-32)
        draw.rounded_rectangle((x-3, 86, x+3, 106), radius=2, fill=TEXT, outline=BG)
        draw.text((16, 126), "Line and shading", fill=TEXT, font=font(12), anchor="lm")
        cell = (self.width-32)/3
        self.style_tiles = {}
        for index, kind in enumerate(LINE_STYLES):
            left, top = int(16+(index%3)*cell), 143+(index//3)*59
            right, bottom = int(left+cell-6), top+51
            self.style_tiles[kind] = (left, top, right, bottom)
            chosen = self.chart.line_styles.get(self.uuid, "Line") == kind
            background = "#2a3a4c" if chosen else PANEL
            draw.rounded_rectangle((left,top,right,bottom), radius=6,
                                   fill=background, outline=color if chosen else GRID)
            preview = Image.new("RGB", (right-left-12, 28), background)
            w = preview.width-1
            points = [(0,22),(w*.25,13),(w*.48,21),(w*.72,4),(w,17)]
            if kind in ("Filled", "Gradient", "Hatched"):
                shade_area(preview, points, color, 27, kind)
            painter = ImageDraw.Draw(preview)
            if kind == "Dashed":
                dashed_series(painter, points, color, 2)
            else:
                painter.line(points, fill=color, width=2)
            self.surface.paste(preview, (left+6,top+4))
            draw.text(((left+right)/2, bottom-10), kind, fill=TEXT if chosen else MUTED, font=font(12), anchor="mm")
        draw.text((16, 282), self.status or "Type a hex color · Enter to confirm", fill=MUTED, font=font(11), anchor="lm")

    def color_at(self, x):
        hue = max(0, min(1, (x-16)/(self.width-32)))
        rgb = tuple(round(v*255) for v in colorsys.hsv_to_rgb(hue, .72, .95))
        self.hex_value.set("#"+"".join(f"{v:02X}" for v in rgb))

    def click(self, event):
        if event.y < 34 and event.x > self.width-40:
            self.close()
        elif 82 <= event.y <= 110:
            self.sliding = True
            self.color_at(event.x)
        else:
            for kind, (left,top,right,bottom) in self.style_tiles.items():
                if left <= event.x <= right and top <= event.y <= bottom:
                    self.chart.line_styles[self.uuid] = kind
                    self.chart.refresh()
                    self.render()
                    break

    def motion(self, event):
        if self.sliding:
            self.color_at(event.x)


class ExportMenu(GlassOverlay):
    def __init__(self, controller, charts, source):
        self.controller, self.charts = controller, list(charts)
        self.chart_index, self.status = 0, ""
        self.chart_tiles, self.gpu_tiles, self.format_tiles = {}, {}, {}
        self.uuid = self.charts[0].focused_uuid or next(iter(controller.devices), None)
        chart_rows = (len(self.charts)+1)//2
        gpu_rows = max(1,(len(controller.devices)+2)//3)
        self.gpu_title_y = 74+chart_rows*42
        self.gpu_top = self.gpu_title_y+18
        self.format_y = self.gpu_top+gpu_rows*37+12
        self.png_y = self.format_y+46
        self.saved_enabled=getattr(controller,'store',None) is not None
        super().__init__(source.winfo_toplevel(), source, 380, self.png_y+(114 if self.saved_enabled else 74))
        self.bind("<Button-1>", self.click)
        self.render()

    def paint(self, draw):
        draw.text((16,22), "Export", fill=TEXT, font=font(16,True), anchor="lm")
        draw.text((self.width-20,22), "×", fill=MUTED, font=font(19), anchor="mm")
        draw.text((16,51), "Data window", fill=MUTED, font=font(12), anchor="lm")
        cell = (self.width-32)/2
        self.chart_tiles = {}
        for index, chart in enumerate(self.charts):
            left, top = int(16+(index%2)*cell), 67+(index//2)*42
            box = (left,top,int(left+cell-6),top+34)
            self.chart_tiles[index] = box
            draw.rounded_rectangle(box, radius=6, fill="#253145" if index==self.chart_index else PANEL,
                                   outline="#56d6be" if index==self.chart_index else GRID)
            draw.text(((box[0]+box[2])/2,top+17), chart.title, fill=TEXT, font=font(12), anchor="mm")
        draw.text((16,self.gpu_title_y), "GPU", fill=MUTED, font=font(12), anchor="lm")
        names = self.charts[self.chart_index].names
        cell = (self.width-32)/3
        self.gpu_tiles = {}
        for index, (uuid,name) in enumerate(names.items()):
            left, top = int(16+(index%3)*cell), self.gpu_top+(index//3)*37
            box = (left,top,int(left+cell-5),top+30)
            self.gpu_tiles[uuid] = box
            color = self.charts[self.chart_index].series_color(uuid)
            draw.rounded_rectangle(box, radius=6, fill="#253145" if uuid==self.uuid else PANEL,
                                   outline=color if uuid==self.uuid else GRID)
            draw.text(((box[0]+box[2])/2,top+15), name, fill=color, font=font(11), anchor="mm")
        if not names:
            draw.text((16,self.gpu_top+15), "Waiting for GPU readings…", fill=MUTED, font=font(12), anchor="lm")
        self.format_tiles = {}
        for index, kind in enumerate(("csv", "pdf")):
            left = int(16+index*(self.width-32)/2)
            box = (left,self.format_y,int(left+(self.width-32)/2-6),self.format_y+34)
            self.format_tiles[kind] = box
            draw.rounded_rectangle(box, radius=6, fill=PANEL, outline=GRID)
            draw.text(((box[0]+box[2])/2,self.format_y+17), kind.upper(), fill=TEXT, font=font(13,True), anchor="mm")
        self.png_tile = (16,self.png_y,self.width-16,self.png_y+32)
        draw.rounded_rectangle(self.png_tile, radius=6, fill=PANEL, outline=GRID)
        draw.text((self.width/2,self.png_y+16), "Save all graphs as PNG" if len(self.charts)>1 else "Save graph as PNG",
                  fill=TEXT, font=font(12), anchor="mm")
        draw.text((16,self.png_y+52), self.status or "CSV/PDF: selected GPU and visible time range", fill=MUTED, font=font(11), anchor="lm")
        self.saved_tile=None
        if self.saved_enabled:
            self.saved_tile=(16,self.png_y+68,self.width-16,self.png_y+100)
            draw.rounded_rectangle(self.saved_tile,radius=6,fill=PANEL,outline=GRID)
            draw.text((self.width/2,self.png_y+84),'Saved history CSV · selected GPU · last 24h',fill=TEXT,font=font(12),anchor='mm')

    def export_selected(self, kind, directory=None):
        if self.uuid is None:
            raise ValueError("Wait for GPU readings before exporting.")
        path = self.charts[self.chart_index].export_series(self.uuid, kind, directory)
        self.status = kind.upper()+" saved in exports/"
        self.render()
        return path

    def click(self, event):
        def inside(box):
            left,top,right,bottom = box
            return left <= event.x <= right and top <= event.y <= bottom
        if event.y < 35 and event.x > self.width-40:
            self.close()
            return
        if self.saved_tile and inside(self.saved_tile):
            try:
                self.controller.export_stored(self.uuid)
                self.status='Exporting saved readings; see the status bar.'
            except (OSError,ValueError,RuntimeError) as error:
                self.status=str(error)[:52]
            self.render()
            return
        for index, box in self.chart_tiles.items():
            if inside(box):
                self.chart_index = index
                self.render()
                return
        for uuid, box in self.gpu_tiles.items():
            if inside(box):
                self.uuid = uuid
                self.render()
                return
        for kind, box in self.format_tiles.items():
            if inside(box):
                try:
                    self.export_selected(kind)
                except (OSError,ValueError) as error:
                    self.status = str(error)[:52]
                    self.render()
                return
        if inside(self.png_tile):
            self.controller.save_images(self.charts)
            self.status = "PNG saved in captures/" if self.controller.notice[1].startswith("Saved") else "Could not save PNG; see the status bar."
            self.render()



class SlimScrollbar(tk.Canvas):
    def __init__(self, parent, orient, command):
        super().__init__(parent, bg=BG, highlightthickness=0, width=9, height=9)
        self.orient, self.command = orient, command
        self.first, self.last, self.grab_offset = 0., 1., 0.
        self.pack_options = {"side": "right", "fill": "y"} if orient=="vertical" else {"side": "bottom", "fill": "x"}
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<Enter>", lambda _: self.draw(True))
        self.bind("<Leave>", lambda _: self.draw())

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        needed = self.last-self.first < .99999
        if needed and not self.winfo_manager():
            self.pack(**self.pack_options)
        elif not needed and self.winfo_manager():
            self.pack_forget()
        self.draw()

    def length(self):
        return max(1, self.winfo_height() if self.orient=="vertical" else self.winfo_width())

    def thumb(self):
        length = self.length()
        size = min(length, max(24, (self.last-self.first)*length))
        fraction_range = max(.00001, 1-(self.last-self.first))
        start = (length-size)*self.first/fraction_range
        return start, size

    def draw(self, hover=False):
        self.delete("all")
        start, size = self.thumb()
        color = "#8a939f" if hover else "#58616e"
        if self.orient == "vertical":
            self.create_oval(2, start, 7, start+5, fill=color, outline="")
            self.create_rectangle(2, start+2, 7, start+size-2, fill=color, outline="")
            self.create_oval(2, start+size-5, 7, start+size, fill=color, outline="")
        else:
            self.create_oval(start, 2, start+5, 7, fill=color, outline="")
            self.create_rectangle(start+2, 2, start+size-2, 7, fill=color, outline="")
            self.create_oval(start+size-5, 2, start+size, 7, fill=color, outline="")

    def click(self, event):
        point = event.y if self.orient=="vertical" else event.x
        start, size = self.thumb()
        self.grab_offset = point-start if start <= point <= start+size else size/2
        self.drag(event)

    def drag(self, event):
        point = event.y if self.orient=="vertical" else event.x
        _, size = self.thumb()
        travel = max(1, self.length()-size)
        fraction = (point-self.grab_offset)/travel*(1-(self.last-self.first))
        self.command("moveto", max(0, min(1-(self.last-self.first), fraction)))
