"""Capture only this application's windows with reproducible synthetic readings.

Windows PrintWindow targets the application HWND; no desktop crop, other apps,
driver query or real workload is captured. Run from the project root.
"""
from pathlib import Path
from datetime import datetime
import ctypes
from ctypes import wintypes
import math
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from dashboard import Dashboard
from gpu_data import Reading, Snapshot
from controls import QuickMenu,SelectMenu


def pump(app, seconds=.4):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.update()
        time.sleep(.01)
    app.redraw()
    app.update_idletasks()


def capture(window, path):
    # Let native child windows finish painting after the final Tk redraw.
    for _ in range(6):
        window.update()
        time.sleep(.05)
    user=ctypes.WinDLL('user32',use_last_error=True)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
    user.GetAncestor.restype=wintypes.HWND
    user.GetWindowDC.argtypes=[wintypes.HWND]
    user.GetWindowDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC]
    gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ]
    gdi.SelectObject.restype=wintypes.HGDIOBJ
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes=[wintypes.HDC]
    hwnd=user.GetAncestor(window.winfo_id(),2)
    width,height=window.winfo_width(),window.winfo_height()
    dc=user.GetWindowDC(hwnd)
    memory=gdi.CreateCompatibleDC(dc)
    bitmap=gdi.CreateCompatibleBitmap(dc,width,height)
    previous=gdi.SelectObject(memory,bitmap)
    try:
        if not user.PrintWindow(hwnd,memory,2):
            raise OSError('PrintWindow could not capture the app window')
        gdi.SelectObject(memory,previous)
        class Header(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),
                      ('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),
                      ('image_size',wintypes.DWORD),('xppm',wintypes.LONG),('yppm',wintypes.LONG),
                      ('used',wintypes.DWORD),('important',wintypes.DWORD)]
        header=Header(ctypes.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        buffer=ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(memory,bitmap,0,height,buffer,ctypes.byref(header),0)!=height:
            raise OSError('Incomplete app capture')
        image=Image.frombuffer('RGB',(width,height),buffer.raw,'raw','BGRX',0,1).copy()
        if all(lo==hi for lo,hi in image.getextrema()):
            raise OSError('Blank app capture')
        image.save(path,optimize=True)
        print(path.name, f'{width}x{height}')
    finally:
        gdi.SelectObject(memory,previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd,dc)


def populate(app):
    now=time.monotonic()
    for i in range(300):
        readings=[]
        for gpu in range(3):
            active=(i//65+gpu)%4!=0
            load=max(1,min(99,(72+17*math.sin(i*.09+gpu)+6*math.sin(i*.61)) if active else 5+3*math.sin(i*.2)))
            memory=(18.4+1.2*math.sin(i*.025+gpu)) if active and gpu<2 else (2.2+.2*math.sin(i*.05))
            temp=39+load*.34+2*math.sin(i*.045+gpu)
            power=17+load*(2.82 if gpu<2 else 1.65)+6*math.sin(i*.23)
            readings.append(Reading(str(gpu),f'DEMO-{gpu}','NVIDIA GeForce RTX 3090' if gpu<2 else 'NVIDIA GeForce RTX 4070',
                                    round(load,2),round(memory,3),24 if gpu<2 else 12,round(temp,2),round(power,2),310 if gpu<2 else 200))
        app.accept(Snapshot(now-299+i,datetime(2026,11,13,10,32).timestamp()-299+i,tuple(readings)))
    app.paused=True
    app.frozen_at=now
    app.window_choice.set('5 minutes')
    app.subtitle.configure(text='DOCUMENTATION DEMO  |  synthetic readings  |  real application UI')
    app.live.configure(text='DEMO',fg='#ffbd69')
    app.status.configure(text='DEMO DATA - synthetic readings for documentation. Live mode reads NVIDIA nvidia-smi.')


def main():
    if os.name!='nt':
        raise SystemExit('Application window captures require Windows.')
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    output=Path(__file__).resolve().parents[1]/'docs'/'images'
    output.mkdir(parents=True,exist_ok=True)
    app=Dashboard(collect=False)
    try:
        app.geometry('1400x1040+40+40')
        populate(app)
        pump(app)
        capture(app,output/'01-dashboard.png')

        chart=app.charts[0]
        chart.focused_uuid='DEMO-1'
        app.apply_gpu_setting(chart,'DEMO-1','styles','Gradient')
        app.apply_gpu_setting(chart,'DEMO-1','opacity',.7)
        pump(app)
        menu=QuickMenu(chart,'DEMO-1',chart.value_labels['DEMO-1'])
        pump(app)
        capture(app,output/'02-line-options.png')
        menu.close()
        chart.focused_uuid=None

        source=app.charts[3]
        source.pins.add(app.history[-155],'DEMO-1')
        source.pins.add(app.history[-45],'DEMO-1')
        window=app.open_window(source)
        window.geometry('1280x900+60+60')
        for child in window.winfo_children():
            for label in child.winfo_children():
                if isinstance(label,tk.Label) and label.cget('text')=='GPU Live Graphs':
                    label.configure(text='GPU Live Graphs  |  DEMO - synthetic readings')
        pump(app)
        capture(window,output/'03-pinned-samples.png')
        window.close()
        source.pins.pins.clear()

        for item in app.charts:
            item.view.zoom=3.0
        pump(app)
        capture(app,output/'04-zoomed-history.png')
        for item in app.charts:
            item.view.zoom=1.0

        chart.time_mode='clock'
        pump(app)
        menu=SelectMenu(app.window_choice)
        capture(app,output/'07-clock-history.png')
        menu.close()

        # Diagnostics demo stays inside ignored build output; no real settings are changed.
        os.environ['GPU_LIVE_GRAPHS_DATA_DIR']=str(Path(__file__).resolve().parents[1]/'build'/'documentation-session')
        menu=app.open_settings()
        menu.path.set('D:\\DEBUGGING LOGS')
        capture(app,output/'08-session-settings.png')
        menu.close()

        app.geometry('760x1100+40+40')
        pump(app)
        capture(app,output/'05-vertical-layout.png')
        app.viewport.yview_moveto(1)
        pump(app)
        capture(app,output/'06-vertical-lower-panels.png')
    finally:
        app.close()


if __name__=='__main__':
    main()
