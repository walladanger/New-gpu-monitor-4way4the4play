"""Frameless Tk window controls and real resize grips.

No Python callback is installed into the Win32 window procedure. Windows calls
are limited to style flags, monitor bounds, placement and minimize/restore.
"""
import ctypes
import os
import tkinter as tk
from ctypes import wintypes

from PIL import Image,ImageDraw,ImageTk

BG,TEXT,MUTED = "#10151d","#e9eff7","#9baabe"


def edge_hit_test(rect,x,y,grip=7,maximized=False):
    if maximized:
        return 1
    left,top,right,bottom=rect
    west,east=x<left+grip,x>=right-grip
    north,south=y<top+grip,y>=bottom-grip
    if north:
        return 13 if west else 14 if east else 12
    if south:
        return 16 if west else 17 if east else 15
    return 10 if west else 11 if east else 1


def resized_bounds(bounds,edge,dx,dy,minimum):
    x,y,width,height=bounds
    left,top,right,bottom=x,y,x+width,y+height
    if "w" in edge: left+=dx
    if "e" in edge: right+=dx
    if "n" in edge: top+=dy
    if "s" in edge: bottom+=dy
    width,height=max(minimum[0],right-left),max(minimum[1],bottom-top)
    if "w" in edge: left=right-width
    if "n" in edge: top=bottom-height
    return left,top,width,height


def fit_bounds(bounds,work_area,minimum=(450,300)):
    x,y,width,height=map(int,bounds)
    left,top,right,bottom=work_area
    width=min(max(minimum[0],width),max(1,right-left))
    height=min(max(minimum[1],height),max(1,bottom-top))
    return min(max(left,x),right-width),min(max(top,y),bottom-height),width,height


class MonitorInfo(ctypes.Structure):
    _fields_=[("cbSize",wintypes.DWORD),("rcMonitor",wintypes.RECT),("rcWork",wintypes.RECT),("dwFlags",wintypes.DWORD)]


class WindowChrome:
    def __init__(self,window,header,drag_widgets=()):
        self.window,self.header=window,header
        self.native,self.error,self.hwnd=False,None,None
        self.maximized=False
        self.normal_bounds=None
        self.last_normal_bounds=None
        self._drag=None
        self._grab_widget=None
        window.overrideredirect(True)
        window.resizable(True,True)
        self.controls=tk.Frame(header,bg=BG)
        self.controls.pack(side="right",padx=(18,0))
        self.buttons={}
        for kind,action in (("minimize",self.minimize),("maximize",self.toggle_maximize),("close",window.close)):
            image=Image.new("RGBA",(18,18))
            draw=ImageDraw.Draw(image)
            if kind=="minimize":
                draw.line((4,10,14,10),fill=MUTED,width=1)
            elif kind=="maximize":
                draw.rectangle((4,4,13,13),outline=MUTED,width=1)
            else:
                draw.line((4,4,13,13),fill=TEXT,width=1)
                draw.line((13,4,4,13),fill=TEXT,width=1)
            control=tk.Button(self.controls,text="",bg=BG,relief="flat",borderwidth=0,highlightthickness=0,
                              padx=8,pady=6,cursor="hand2",command=action,
                              activebackground="#56313c" if kind=="close" else "#253145")
            control.icon=ImageTk.PhotoImage(image,master=window)
            control.configure(image=control.icon)
            control.pack(side="left",padx=1)
            self.buttons[kind]=control
        for widget in (header,)+tuple(drag_widgets):
            self.bind_drag(widget)
        self.grips={}
        for edge,cursor in (("w","sb_h_double_arrow"),("e","sb_h_double_arrow"),
                            ("n","sb_v_double_arrow"),("s","sb_v_double_arrow"),
                            ("nw","top_left_corner"),("ne","top_right_corner"),
                            ("sw","bottom_left_corner"),("se","bottom_right_corner")):
            grip=tk.Frame(window,bg=BG,cursor=cursor,borderwidth=0,highlightthickness=0)
            grip._ambient_exempt=True
            grip._resize_edge=edge
            grip.bind("<ButtonPress-1>",lambda event,e=edge:self.begin_resize(event,e))
            grip.bind("<B1-Motion>",self.resize_motion)
            grip.bind("<ButtonRelease-1>",self.end_drag)
            self.grips[edge]=grip
        window.update_idletasks()
        if os.name=="nt":
            try:
                self.install_windows()
            except (OSError,AttributeError) as error:
                self.error=str(error)
        self.map_binding=window.bind("<Map>",self.on_map,add="+")
        self.configure_binding=window.bind("<Configure>",self.on_configure,add="+")
        window.bind("<Alt-F4>",lambda _:window.close(),add="+")
        self.layout_grips()

    def bind_drag(self,widget):
        widget._window_drag=self
        widget.bind("<ButtonPress-1>",self.begin_drag,add="+")
        widget.bind("<B1-Motion>",self.drag_motion,add="+")
        widget.bind("<ButtonRelease-1>",self.end_drag,add="+")
        widget.bind("<Double-Button-1>",lambda _:self.toggle_maximize(),add="+")

    def install_windows(self):
        self.user=ctypes.WinDLL("user32",use_last_error=True)
        self.user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
        self.user.GetAncestor.restype=wintypes.HWND
        self.user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.user.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
        self.user.IsIconic.argtypes=[wintypes.HWND]
        self.user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        self.user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
        self.user.MonitorFromWindow.restype=wintypes.HANDLE
        self.user.MonitorFromRect.argtypes=[ctypes.POINTER(wintypes.RECT),wintypes.DWORD]
        self.user.MonitorFromRect.restype=wintypes.HANDLE
        self.user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        self.get_style=getattr(self.user,"GetWindowLongPtrW",self.user.GetWindowLongW)
        self.get_style.argtypes=[wintypes.HWND,ctypes.c_int]
        self.get_style.restype=ctypes.c_ssize_t
        self.set_style=getattr(self.user,"SetWindowLongPtrW",self.user.SetWindowLongW)
        self.set_style.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        self.set_style.restype=ctypes.c_ssize_t
        self.native=True
        self.configure_taskbar()

    def configure_taskbar(self):
        self.hwnd=self.user.GetAncestor(self.window.winfo_id(),2)
        # App-window style retains a taskbar entry for the borderless Tk wrapper.
        extended=self.get_style(self.hwnd,-20)
        self.set_style(self.hwnd,-20,(extended&~0x80)|0x40000)
        style=self.get_style(self.hwnd,-16)
        self.set_style(self.hwnd,-16,style|0x80000|0x20000|0x10000)
        self.user.SetWindowPos(self.hwnd,None,0,0,0,0,0x1|0x2|0x4|0x10|0x20)

    def on_map(self,event):
        if event.widget is self.window:
            if self.native:
                self.configure_taskbar()
            self.layout_grips()

    def on_configure(self,event):
        if event.widget is self.window:
            self.layout_grips()

    def layout_grips(self):
        if self.maximized:
            for grip in self.grips.values():
                grip.place_forget()
            return
        positions={
            "w":dict(x=0,y=12,width=7,relheight=1,height=-24),
            "e":dict(relx=1,x=-7,y=12,width=7,relheight=1,height=-24),
            "n":dict(x=12,y=0,relwidth=1,width=-24,height=7),
            "s":dict(x=12,rely=1,y=-7,relwidth=1,width=-24,height=7),
            "nw":dict(x=0,y=0,width=12,height=12),
            "ne":dict(relx=1,x=-12,y=0,width=12,height=12),
            "sw":dict(x=0,rely=1,y=-12,width=12,height=12),
            "se":dict(relx=1,rely=1,x=-12,y=-12,width=12,height=12)}
        for edge,position in positions.items():
            grip=self.grips[edge]
            grip.place(**position)
            grip.tk.call("raise",grip._w)

    def bounds(self):
        return self.window.winfo_rootx(),self.window.winfo_rooty(),self.window.winfo_width(),self.window.winfo_height()

    def preference_bounds(self):
        if self.maximized and self.normal_bounds:
            return self.normal_bounds
        if self.is_minimized() and self.last_normal_bounds:
            return self.last_normal_bounds
        self.last_normal_bounds=self.bounds()
        return self.last_normal_bounds

    def restore_bounds(self,bounds,maximized=False):
        area=(0,0,self.window.winfo_screenwidth(),self.window.winfo_screenheight())
        if self.native:
            x,y,width,height=bounds
            rect=wintypes.RECT(x,y,x+width,y+height)
            info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
            monitor=self.user.MonitorFromRect(ctypes.byref(rect),2)
            if self.user.GetMonitorInfoW(monitor,ctypes.byref(info)):
                work=info.rcWork
                area=work.left,work.top,work.right,work.bottom
        self.set_bounds(fit_bounds(bounds,area,self.window.minsize()))
        self.window.update_idletasks()
        if maximized and not self.maximized:
            self.toggle_maximize()

    def set_bounds(self,bounds):
        x,y,width,height=map(int,bounds)
        if self.native:
            self.hwnd=self.user.GetAncestor(self.window.winfo_id(),2)
            if not self.user.SetWindowPos(self.hwnd,None,x,y,width,height,0x4|0x10):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            self.window.geometry(f"{width}x{height}{x:+}{y:+}")

    def begin_resize(self,event,edge):
        if not self.maximized:
            self._drag=("resize",edge,event.x_root,event.y_root,self.bounds())
            self._grab_widget=event.widget
            event.widget.grab_set()
        return "break"

    def resize_motion(self,event):
        if self._drag and self._drag[0]=="resize":
            _,edge,x,y,bounds=self._drag
            self.set_bounds(resized_bounds(bounds,edge,event.x_root-x,event.y_root-y,self.window.minsize()))
        return "break"

    def begin_drag(self,event):
        self._drag=("move",None,event.x_root,event.y_root,self.bounds())
        self._grab_widget=event.widget
        event.widget.grab_set()
        return "break"

    def drag_motion(self,event):
        if self._drag and self._drag[0]=="move":
            _,_,x,y,bounds=self._drag
            if self.maximized:
                fraction=(x-bounds[0])/max(1,bounds[2])
                target=self.normal_bounds
                self.maximized=False
                bounds=(round(x-target[2]*fraction),y-min(40,y-bounds[1]),target[2],target[3])
                self._drag=("move",None,x,y,bounds)
                self.layout_grips()
            self.set_bounds((bounds[0]+event.x_root-x,bounds[1]+event.y_root-y,bounds[2],bounds[3]))
        return "break"

    def end_drag(self,event=None):
        # Very quick drags can coalesce all motion events before release.
        # Commit the final pointer position even when no B1-Motion arrived.
        if event is not None and self._drag:
            if self._drag[0]=="resize":
                self.resize_motion(event)
            else:
                self.drag_motion(event)
        if self._grab_widget:
            try:
                self._grab_widget.grab_release()
            except tk.TclError:
                pass
            self._grab_widget=None
        self._drag=None
        return "break"

    def is_maximized(self):
        return self.maximized

    def is_minimized(self):
        return bool(self.user.IsIconic(self.hwnd)) if self.native else self.window.state()=="iconic"

    def minimize(self):
        self.end_drag()
        if not self.maximized:
            self.last_normal_bounds=self.bounds()
        if self.native:
            self.user.ShowWindow(self.hwnd,6)
        else:
            self.window.overrideredirect(False)
            self.window.iconify()

    def restore(self):
        if self.native:
            self.user.ShowWindow(self.hwnd,9)
        else:
            self.window.deiconify()
            self.window.overrideredirect(True)

    def toggle_maximize(self):
        self.end_drag()
        if self.maximized:
            self.maximized=False
            self.set_bounds(self.normal_bounds)
        else:
            self.normal_bounds=self.bounds()
            target=(0,0,self.window.winfo_screenwidth(),self.window.winfo_screenheight())
            if self.native:
                info=MonitorInfo()
                info.cbSize=ctypes.sizeof(info)
                monitor=self.user.MonitorFromWindow(self.hwnd,2)
                if self.user.GetMonitorInfoW(monitor,ctypes.byref(info)):
                    rect=info.rcWork
                    target=(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)
            self.maximized=True
            self.set_bounds(target)
        self.layout_grips()
        return "break"

    def client_insets(self):
        if not self.native:
            return None
        outer,client,origin=wintypes.RECT(),wintypes.RECT(),wintypes.POINT()
        self.user.GetWindowRect(self.hwnd,ctypes.byref(outer))
        self.user.GetClientRect(self.hwnd,ctypes.byref(client))
        self.user.ClientToScreen(self.hwnd,ctypes.byref(origin))
        return origin.x-outer.left,origin.y-outer.top,outer.right-origin.x-client.right,outer.bottom-origin.y-client.bottom

    def detach(self):
        self.end_drag()
        self.window.unbind("<Map>",self.map_binding)
        self.window.unbind("<Configure>",self.configure_binding)
        self.native=False
