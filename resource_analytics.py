"""System resource dial and occupancy-heatmap visualizations.

Heatmap intensity is *recorded dwell time* in a value/time bin. It never
manufactures missing telemetry or treats high utilization as time spent.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

from PIL import Image, ImageDraw

from graph_scene import PANEL, GRID, TEXT, MUTED, font
from system_graph import series_label

GAUGE_STYLES=("Ring","Pie","Arc")
GAUGE_DEFAULTS=("cpu:total","cpu:clock","ram:used_pct","disk:total:read")
METRIC_UNITS={"cpu:total":"%","cpu:clock":"GHz","ram:used_pct":"%",
              "ram:used":"GiB","ram:available":"GiB","ram:cached":"GiB","ram:total":"GiB"}
HEATMAP_DEFAULT="cpu:total"
HEATMAP_WINDOWS={"1 minute":60,"5 minutes":300,"15 minutes":900,"1 hour":3600}


@dataclass
class GaugeSpec:
    metric: str
    style: str = "Ring"
    color: str = "#56D6BE"


def metric_unit(key):
    if key in METRIC_UNITS or key.startswith("cpu:thread:"):
        return METRIC_UNITS.get(key,"%")
    if key.endswith(":read") or key.endswith(":write"):
        return "MiB/s"
    if key.startswith("disk:volume:"):
        return "GiB"
    return ""


def metric_value(key,snapshot):
    return (snapshot.values.get(key) if snapshot else None, metric_unit(key))


def available_metrics(history,known=()):
    found=set(known)
    for snapshot in history:
        found.update(k for k in snapshot.values if isinstance(k,str) and (
            k.startswith("cpu:") or k.startswith("ram:") or k.startswith("disk:")))
    ordered=[key for key in GAUGE_DEFAULTS if key in found]
    ordered.extend(sorted(found-set(ordered),key=lambda s:(0 if s.startswith("cpu:thread:") else 1,s)))
    return tuple(ordered)


def gauge_limit(key,history):
    if key=="cpu:total" or key=="ram:used_pct" or key.startswith("cpu:thread:"):
        return 100.0
    if key=="cpu:clock":
        speeds=[s.values.get(key) for s in history]
        seen=[v for v in speeds if isinstance(v,(int,float)) and math.isfinite(v) and v>0]
        return max(1.0,math.ceil(max(seen or [1.0])*10)/10)
    if key.startswith("ram:") and not key.endswith(":used_pct"):
        totals=[s.values.get("ram:total") for s in history]
        limits=[v for v in totals if isinstance(v,(int,float)) and v>0]
        if limits:
            return max(limits)
    if key.startswith('disk:volume:'):
        total_key=key.rsplit(':',1)[0]+':total'
        totals=[s.values.get(total_key) for s in history]
        limits=[v for v in totals if _valid_reading(v) and v>0]
        if limits:
            return max(limits)
    values=[s.values.get(key) for s in history]
    seen=[v for v in values if isinstance(v,(int,float)) and math.isfinite(v) and v>0]
    return max(1.0,max(seen or [1.0]))


def render_gauge(width,height,value,limit,label,color,style):
    width,height=max(60,int(width)),max(60,int(height))
    image=Image.new("RGB",(width,height),PANEL)
    draw=ImageDraw.Draw(image)
    value=value if isinstance(value,(int,float)) and math.isfinite(value) and value>=0 else None
    progress=max(0,min(1,value/limit)) if value is not None and limit>0 else 0
    side=min(width,height)
    thick=max(7,round(side*.09))
    margin=max(13,round(side*.13))
    radius=side/2-margin
    oval=(width/2-radius,height/2-radius,width/2+radius,height/2+radius)
    if style not in GAUGE_STYLES:
        style="Ring"
    if style=="Pie":
        draw.ellipse(oval,fill=GRID)
        if progress>0:
            draw.pieslice(oval,start=-90,end=-90+360*progress,fill=color)
        middle=(width*.5,height*.5)
        inner=side*.24
        draw.ellipse((middle[0]-inner,middle[1]-inner,
                      middle[0]+inner,middle[1]+inner),fill=PANEL)
    else:
        sweep=270 if style=="Arc" else 360
        start=135 if style=="Arc" else -90
        draw.arc(oval,start=start,end=start+sweep,fill=GRID,width=thick)
        if progress>0:
            draw.arc(oval,start=start,end=start+sweep*progress,fill=color,width=thick)
    draw.text((width/2,height/2-4),label,fill=TEXT,font=font(max(12,min(20,round(side*.13))),True),anchor="mm")
    return image


def _valid_reading(value):
    return isinstance(value,(int,float)) and math.isfinite(value) and value>=0


def metric_bounds(history,metric,now,seconds):
    relevant=[s.values.get(metric) for s in history if now-seconds-2.5<=s.stamp<=now and _valid_reading(s.values.get(metric))]
    high=100.0 if metric in ('cpu:total','ram:used_pct') or metric.startswith('cpu:thread:') else max(1.0,max(relevant or [1.0]))
    # Clock differences of a few tenths of a GHz should occupy distinct bands.
    low=min(relevant) if metric=='cpu:clock' and relevant else 0.0
    if low>=high:
        low=max(0,high-.5)
    return low,high


def occupancy_bins(history,metric,now,seconds,columns=20,bands=10):
    """Count observed seconds in each time/value cell using sample-hold intervals.

    An interval contributes only if the next sample is no more than 2.5s
    later; gaps are not silently filled. Samples do not get interpolated.
    """
    if not 2<=columns<=100 or not 2<=bands<=100 or seconds<=0:
        raise ValueError("Invalid occupancy bin layout")
    rows=[[0.0]*columns for _ in range(bands)]
    history=tuple(sorted(history,key=lambda s:s.stamp))
    start=now-seconds
    low,scale=metric_bounds(history,metric,now,seconds)
    bucket_size=seconds/columns
    for previous,current in zip(history,history[1:]):
        gap=current.stamp-previous.stamp
        if gap<=0 or gap>2.5:
            continue
        value=previous.values.get(metric)
        if not _valid_reading(value):
            continue
        left=max(start,previous.stamp)
        right=min(now,current.stamp)
        if right<=left:
            continue
        band=max(0,min(bands-1,int(min((value-low)/(scale-low),1)*bands)))
        first=max(0,min(columns-1,int((left-start)/bucket_size)))
        last=max(0,min(columns-1,int((right-start-1e-12)/bucket_size)))
        for column in range(first,last+1):
            cell_left=max(left,start+column*bucket_size)
            cell_right=min(right,start+(column+1)*bucket_size)
            if cell_right>cell_left:
                rows[band][column]+=cell_right-cell_left
    return rows,scale


def _mix(a,b,amount):
    p=tuple(int(a[k:k+2],16) for k in (1,3,5))
    q=tuple(int(b[k:k+2],16) for k in (1,3,5))
    out=tuple(round(x*(1-amount)+y*amount) for x,y in zip(p,q))
    return "#" + "".join(f"{value:02X}" for value in out)


def intensity_color(fraction):
    if fraction<=0:
        return PANEL
    fraction=max(0,min(1,fraction))
    # Occupancy density increases from yellow -> bright red -> deep purple.
    if fraction<=.55:
        return _mix("#FCD34D","#EF4444",fraction/.55)
    return _mix("#EF4444","#6D28D9",(fraction-.55)/.45)


def render_occupancy(width,height,history,metric,now,seconds,columns=24,bands=12):
    width,height=max(320,int(width)),max(180,int(height))
    image=Image.new("RGB",(width,height),PANEL)
    draw=ImageDraw.Draw(image)
    matrix,scale=occupancy_bins(history,metric,now,seconds,columns,bands)
    low,_=metric_bounds(history,metric,now,seconds)
    label=series_label(metric)
    units=metric_unit(metric)
    draw.text((16,12),f"TIME OCCUPANCY  ·  {label} ({units})",font=font(13,True),fill=TEXT)
    left,top,right,bottom=76,46,width-19,height-52
    cell_width=(right-left)/columns
    cell_height=(bottom-top)/bands
    interval=seconds/columns
    for band in range(bands):
        for bucket in range(columns):
            t=matrix[band][bucket]
            x1=round(left+bucket*cell_width)+1
            x2=round(left+(bucket+1)*cell_width)-1
            y1=round(top+(bands-1-band)*cell_height)+1
            y2=round(top+(bands-band)*cell_height)-1
            if x2>=x1 and y2>=y1:
                draw.rectangle((x1,y1,x2,y2),fill=intensity_color(t/interval))
    draw.text((left-9,top+4),f"{scale:g}",fill=MUTED,font=font(10),anchor="rm")
    draw.text((left-9,bottom),f'{low:g}',fill=MUTED,font=font(10),anchor="rm")
    draw.text((left,bottom+13),f"-{round(seconds/60,1):g}m",fill=MUTED,font=font(10),anchor="lm")
    draw.text((right,bottom+13),"Now",fill=MUTED,font=font(10),anchor="rm")
    draw.text((left,height-16),"Duration in each range: ",fill=MUTED,font=font(10),anchor="lm")
    for i,shade in enumerate(("#FCD34D","#EF4444","#6D28D9")):
        x=left+155+i*58
        draw.rectangle((x,height-21,x+27,height-11),fill=shade)
    draw.text((min(right,left+350),height-16),"more time →",fill=MUTED,font=font(10),anchor="lm")
    return image
