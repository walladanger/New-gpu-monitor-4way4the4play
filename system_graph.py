"""Pillow system metric charts, styled like the existing GPU graphs.

The source of every plotted point is a real sampled value; no interpolation or
synthetic samples are inserted across missing readings or timestamp gaps.
"""
from __future__ import annotations
import math

from PIL import Image, ImageDraw

from graph_scene import BG, PANEL, GRID, MUTED, TEXT, font, time_axis, shade_area, dashed_series
from chart_view import LINE_STYLES

MODE_PREFIXES={
    "cpu_percent": ("cpu:total","cpu:thread:"),
    "cpu_clock": ("cpu:clock",),
    "ram_percent": ("ram:used_pct",),
    "ram_capacity": ("ram:used","ram:available","ram:cached"),
    "disk_rate": ("disk:total:","disk:physical:"),
    "disk_capacity": ("disk:volume:",),
}
MODE_UNITS={
    "cpu_percent":"%","cpu_clock":"GHz",
    "ram_percent":"%","ram_capacity":"GiB",
    "disk_rate":"MiB/s","disk_capacity":"GiB",
}


def valid_series(mode,key):
    if mode not in MODE_PREFIXES:
        return False
    return any(key == prefix or key.startswith(prefix)
               for prefix in MODE_PREFIXES[mode])


def available_series(mode,history):
    keys=set()
    for snapshot in history:
        keys.update(k for k in snapshot.values if valid_series(mode,k))
    def sort_key(key):
        if key.startswith("cpu:thread:"):
            try:
                return ("cpu:thread:",int(key.rsplit(":",1)[1]))
            except ValueError:
                pass
        return (key,0)
    return tuple(sorted(keys,key=sort_key))


def series_label(key):
    if key=="cpu:total":
        return "CPU total"
    if key=="cpu:clock":
        return "Reported CPU clock"
    if key.startswith("cpu:thread:"):
        return f"Logical CPU {int(key.rsplit(':',1)[1])+1}"
    names={"ram:used":"RAM used","ram:available":"RAM available",
           "ram:cached":"Cached RAM","ram:used_pct":"RAM used",
           "disk:total:read":"All disks · read","disk:total:write":"All disks · write"}
    if key in names:
        return names[key]
    if key.startswith("disk:physical:"):
        _,_,drive,operation=key.split(":",3)
        return f"{drive} · {operation}"
    if key.startswith("disk:volume:"):
        _,_,volume,metric=key.split(":",3)
        return f"Volume {volume}: · {metric}"
    return key


def render_system_graph(mode,width,height,history,selected,colors,styles,right,seconds,
                        background=None):
    width,height=max(100,int(width)),max(100,int(height))
    image=background.copy() if background is not None else Image.new("RGB",(width,height),PANEL)
    draw=ImageDraw.Draw(image)
    left,top,right_edge,bottom=52,18,width-18,height-35
    selected=tuple(k for k in selected if valid_series(mode,k))
    visible=tuple(snapshot for snapshot in history if right-seconds<=snapshot.stamp<=right)
    values=[snapshot.values.get(key) for snapshot in visible for key in selected]
    finite=[v for v in values if isinstance(v,(int,float)) and math.isfinite(v) and v>=0]
    ceiling=100 if mode in ("cpu_percent","ram_percent") else max([1]+finite)*1.12
    if mode not in ("cpu_percent","ram_percent"):
        ceiling=max(1,math.ceil(ceiling*10)/10)
    axis=font(11)
    for i in range(5):
        y=bottom-(bottom-top)*i/4
        draw.line((left,y,right_edge,y),fill=GRID,width=1)
        label=f"{ceiling*i/4:.2f}".rstrip("0").rstrip(".")
        draw.text((left-7,y),label,fill=MUTED,font=axis,anchor="rm")
    for fraction,label in time_axis(visible,seconds,right,right,"clock"):
        x=left+(right_edge-left)*fraction
        if 0<=fraction<=1:
            draw.line((x,top,x,bottom),fill=GRID,width=1)
            draw.text((x,bottom+18),label,fill=MUTED,font=axis,anchor="mm")
    if not visible or not finite or not selected:
        message="Select one or more sensors" if not selected else "Waiting for recorded sensor values"
        draw.text(((left+right_edge)/2,(top+bottom)/2),message,
                  fill=MUTED,font=font(13),anchor="mm")
        return image

    for key in selected:
        color=colors.get(key,TEXT)
        style=styles.get(key,"Line")
        if style not in LINE_STYLES:
            style="Line"
        segment=[]
        previous=None

        def flush():
            if not segment:
                return
            if len(segment)==1:
                x,y=segment[0]
                draw.ellipse((x-2,y-2,x+2,y+2),fill=color)
            elif style=="Dashed":
                dashed_series(draw,segment,color,2)
            else:
                if style in ("Filled","Gradient","Hatched"):
                    shade_area(image,segment,color,bottom,style)
                draw.line(segment,fill=color,width=2)
            segment.clear()

        for snapshot in visible:
            value=snapshot.values.get(key)
            if (not isinstance(value,(int,float)) or not math.isfinite(value) or
                    value<0 or (previous is not None and snapshot.stamp-previous>2.5)):
                flush()
            if isinstance(value,(int,float)) and math.isfinite(value) and value>=0:
                x=left+(snapshot.stamp-right+seconds)/seconds*(right_edge-left)
                y=bottom-value/ceiling*(bottom-top)
                segment.append((x,y))
            previous=snapshot.stamp
        flush()
    return image
