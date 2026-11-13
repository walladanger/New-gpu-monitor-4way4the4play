"""Graph painting and frosted inspectors, rendered from our own chart data.

Blur is applied to the actual freshly drawn graph beneath each inspector.
No desktop screenshots, native transparency tricks, or other apps are read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
import math
import os
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from gpu_data import Pin, Snapshot, METRICS, compare_pins, gpu_labels

BG = "#10151d"
PANEL = "#181f2a"
TEXT = "#e9eff7"
MUTED = "#9baabe"
GRID = "#2b3544"
COLORS = ("#56d6be", "#70a9ff", "#ffbd69", "#df94ee", "#ff8792", "#c2db79")


@lru_cache(maxsize=32)
def font(size=12, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default(size=size)


def exact(key, value):
    if value is None:
        return "unavailable"
    if key == "memory":
        return f"{value:.10g}"
    return f"{value:g}" if key == "utilization" else f"{value:.2f}"


def delta(key, value):
    if value is None:
        return "n/a"
    return f"{value:+.6f}".rstrip("0").rstrip(".") if key == "memory" else f"{value:+.2f}"


@dataclass
class HitPoint:
    x: float
    y: float
    snapshot: Snapshot
    uuid: str


@dataclass
class Scene:
    image: Image.Image
    points: list[HitPoint] = field(default_factory=list)
    markers: list[tuple[float, float, str]] = field(default_factory=list)
    rows: list[tuple[tuple[int, int, int, int], str]] = field(default_factory=list)
    inspector: tuple[int, int, int, int] | None = None
    row_count: int = 0
    scroll_max: int = 0
    scroll_offset: int = 0
    segments: list = field(default_factory=list)
    hit_index: dict = field(default_factory=dict)
    preferred_uuid: str | None = None

    def index_hits(self):
        self.hit_index={}
        for a,b in [(p,p) for p in self.points]+self.segments:
            for bucket in range(int(min(a.x,b.x)//32),int(max(a.x,b.x)//32)+1):
                self.hit_index.setdefault(bucket,[]).append((a,b))

    def nearest(self, x, y, radius=18):
        candidates=[]
        if self.hit_index:
            for bucket in range(int((x-radius)//32),int((x+radius)//32)+1):
                candidates.extend(self.hit_index.get(bucket,()))
        else:
            candidates=[(p,p) for p in self.points]+self.segments
        best,score=None,None
        seen=set()
        for a,b in candidates:
            identity=(id(a),id(b))
            if identity in seen: continue
            seen.add(identity)
            dx,dy=b.x-a.x,b.y-a.y
            length=dx*dx+dy*dy
            fraction=max(0,min(1,((x-a.x)*dx+(y-a.y)*dy)/length)) if length else 0
            distance=(a.x+fraction*dx-x)**2+(a.y+fraction*dy-y)**2
            if distance>radius*radius: continue
            point=a if fraction<=.5 else b
            candidate=(distance,0 if point.uuid==self.preferred_uuid else 1,(point.x-x)**2+(point.y-y)**2)
            if score is None or candidate<score:
                best,score=point,candidate
        return best


    def pin_at(self, x, y):
        for (left, top, right, bottom), label in self.rows:
            if left <= x <= right and top <= y <= bottom:
                return label
        if self.over_inspector(x, y):
            return None
        return next((label for px, py, label in self.markers if (px-x)**2+(py-y)**2 <= 18**2), None)

    def over_inspector(self, x, y):
        return bool(self.inspector and self.inspector[0] <= x <= self.inspector[2]
                    and self.inspector[1] <= y <= self.inspector[3])


def time_axis(history,seconds,right,clock_now=None,mode='relative'):
    if mode!='clock':
        ticks=[]
        for step in range(5):
            age=seconds*(1-step/4)+(0 if clock_now is None else clock_now-right)
            label='now' if abs(age)<.05 else f'-{age:.3g}s' if age<60 else f'-{age/60:.3g}m'
            ticks.append((step/4,label))
        return ticks
    anchor=history[-1] if history else None
    right_wall=anchor.wall_time+(right-anchor.stamp) if anchor else time.time()+(right-time.monotonic())
    left_wall=right_wall-seconds
    interval=next((n for n in (.1,.2,.5,1,2,5,10,15,30,60,120,300,600,900,1800,3600) if n>=seconds/5),3600)
    start=math.ceil(left_wall/interval)*interval
    left_date=datetime.fromtimestamp(left_wall).astimezone()
    right_date=datetime.fromtimestamp(right_wall).astimezone()
    crossing_day=left_date.date()!=right_date.date()
    crossing_offset=left_date.utcoffset()!=right_date.utcoffset()
    ticks=[]
    for index in range(8):
        wall=start+index*interval
        if wall>right_wall+.0001: break
        date=datetime.fromtimestamp(wall).astimezone()
        label=date.strftime('%I:%M %p').lstrip('0') if interval>=60 else date.strftime('%I:%M:%S %p').lstrip('0')
        if interval<1:
            label=date.strftime('%I:%M:%S').lstrip('0')+f'.{date.microsecond//1000:03d} '+date.strftime('%p')
        if crossing_day: label=date.strftime('%b %d')+'\n'+label
        if crossing_offset: label+=' '+date.strftime('%Z')
        ticks.append(((wall-left_wall)/seconds,label))
    return ticks



def dashed(draw, coords, fill, dash=4, gap=5):
    x1, y1, x2, y2 = coords
    length = math.hypot(x2-x1, y2-y1)
    if not length:
        return
    for start in range(0, math.ceil(length), dash + gap):
        end = min(start + dash, length)
        draw.line((x1+(x2-x1)*start/length, y1+(y2-y1)*start/length,
                   x1+(x2-x1)*end/length, y1+(y2-y1)*end/length), fill=fill)


def dashed_series(draw, points, fill, width):
    phase = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = math.hypot(x2-x1, y2-y1)
        offset = 0.0
        while offset < length:
            run = min(length-offset, (7-phase) if phase < 7 else (12-phase))
            if phase < 7:
                a, b = offset/length, (offset+run)/length
                draw.line((x1+(x2-x1)*a, y1+(y2-y1)*a, x1+(x2-x1)*b, y1+(y2-y1)*b), fill=fill, width=width)
            offset += run
            phase = (phase+run)%12


def shade_area(image, points, color, bottom, kind):
    rgb = tuple(int(color[i:i+2],16) for i in (1,3,5)) if isinstance(color,str) else color
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).polygon([(points[0][0],bottom)]+points+[(points[-1][0],bottom)], fill=255)
    overlay = Image.new("RGBA", image.size)
    painter = ImageDraw.Draw(overlay)
    if kind == "Gradient":
        top = max(0, int(min(y for _,y in points)))
        for y in range(top, int(bottom)+1):
            alpha = round(105*(bottom-y)/max(1,bottom-top))
            painter.line((0,y,image.width,y), fill=rgb+(alpha,))
    elif kind == "Hatched":
        painter.rectangle((0,0,image.width,image.height), fill=rgb+(16,))
        for start in range(-image.height, image.width, 10):
            painter.line((start,image.height,start+image.height,0), fill=rgb+(95,), width=1)
    else:
        painter.rectangle((0,0,image.width,image.height), fill=rgb+(52,))
    overlay.putalpha(ImageChops.multiply(overlay.getchannel("A"), mask))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def render_graph(key, width, height, history, devices, colors, selected, seconds, now,
                 pins=(), inspector_position=None, row_offset=0, active_pin=None, text_scale=1.0,
                 focused=None, line_styles=None, clock_now=None, background=None, opacities=None, time_mode='relative'):
    width, height = max(100, width), max(100, height)
    image = background.copy() if background is not None else Image.new("RGB", (width, height), PANEL)
    scene = Scene(image)
    scene.preferred_uuid=focused
    draw = ImageDraw.Draw(image)
    small = font(round(12 * text_scale))
    left, right, top, bottom = 48, width - 15, 16, height - 30
    ids = {uid for uid in devices if selected is None or uid == selected}
    visible = [snapshot for snapshot in history if now - seconds <= snapshot.stamp <= now]
    ceiling = 100 if key in ("utilization", "temperature") else 1
    if key == "memory":
        ceiling = max([devices[uid].capacity or 1 for uid in ids] + [1])
    elif key == "power":
        ceiling = max([devices[uid].power_limit or 100 for uid in ids] + [100])
    for snapshot in visible:
        for reading in snapshot.readings:
            value = getattr(reading, key)
            if reading.uuid in ids and value is not None:
                ceiling = max(ceiling, value)
    ceiling = math.ceil(ceiling)
    for step in range(5):
        y = bottom - (bottom - top) * step / 4
        draw.line((left, y, right, y), fill=GRID)
        draw.text((left-9, y), f"{ceiling*step/4:g}", fill=MUTED, font=small, anchor="rm")
    for fraction,label in time_axis(history,seconds,now,clock_now,time_mode):
        x = left + (right-left) * fraction
        dashed(draw, (x, top, x, bottom), GRID, 2, 5)
        draw.text((x, bottom+16), label, fill=MUTED, font=small,
                  anchor='rm' if fraction>.94 else 'lm' if fraction<.06 else 'mm')
    locations = {}
    for uid in sorted(ids, key=lambda uid: uid == focused):
        opacity=max(0,min(1,(opacities or {}).get(uid,1)))
        if opacity==0: continue
        before=image.copy() if opacity<1 else None
        segment, previous = [], None
        previous_hit=None
        color = colors[uid]
        if focused and uid != focused:
            background = tuple(int(PANEL[i:i+2], 16) for i in (1, 3, 5))
            rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            color = tuple(round(b+(v-b)*0.25) for b, v in zip(background, rgb))
        weight = 3 if uid == focused else 2
        kind = (line_styles or {}).get(uid, "Line")

        def flush():
            nonlocal previous_hit
            if len(segment) > 1:
                if kind in ("Filled", "Gradient", "Hatched"):
                    shade_area(image, segment, color, bottom, kind)
                    draw.line(segment, fill=color, width=weight)
                elif kind == "Dashed":
                    dashed_series(draw, segment, color, weight)
                else:
                    draw.line(segment, fill=color, width=weight)
            elif segment:
                x, y = segment[0]
                draw.ellipse((x-2, y-2, x+2, y+2), fill=color)
            segment.clear()
            previous_hit=None

        for snapshot in visible:
            reading = snapshot.gpu(uid)
            value = getattr(reading, key) if reading else None
            if value is None or (previous is not None and snapshot.stamp-previous > 2.5):
                flush()
            if value is not None:
                x = left + (snapshot.stamp-now+seconds)/seconds*(right-left)
                y = bottom - value/ceiling*(bottom-top)
                segment.append((x, y))
                hit=HitPoint(x,y,snapshot,uid)
                scene.points.append(hit)
                if previous_hit is not None:
                    scene.segments.append((previous_hit,hit))
                previous_hit=hit
                locations[(snapshot.stamp, uid)] = (x, y)
            previous = snapshot.stamp
        flush()
        if before is not None:
            image.paste(Image.blend(before,image,opacity))
    shown_pins = []
    for pin in pins:
        point = locations.get((pin.snapshot.stamp, pin.uuid))
        if point is None:
            continue
        shown_pins.append(pin)
        x, y = point
        color = colors[pin.uuid]
        dashed(draw, (x, top, x, bottom), color, 3, 6)
        draw.ellipse((x-5, y-5, x+5, y+5), fill=PANEL, outline=TEXT, width=2)
        draw.ellipse((x-2, y-2, x+2, y+2), fill=color)
        label_x = max(left+10, min(right-12, x+10))
        label_y = max(top+12, min(bottom-12, y-16))
        draw.rounded_rectangle((label_x-8, label_y-9, label_x+10, label_y+9), radius=4, fill=color)
        draw.text((label_x+1, label_y), pin.label, fill=BG, font=small, anchor="mm")
        scene.markers.extend(((x, y, pin.label), (label_x, label_y, pin.label)))
    if not scene.points:
        draw.text(((left+right)/2, (top+bottom)/2), "Waiting for readings" if not history else "No readings available",
                  fill=MUTED, font=font(round(14*text_scale)), anchor="mm")
    if shown_pins:
        paint_inspector(scene, shown_pins, key, colors, inspector_position, row_offset, active_pin, text_scale, gpu_labels(devices))
    scene.index_hits()
    return scene


def paint_inspector(scene, pins, key, colors, position, row_offset, active_pin, scale, names):
    image = scene.image
    width, height = image.size
    small, bold = font(round(12*scale)), font(round(13*scale), True)
    line = max(17, round(18*scale))
    row_height = line*3+8
    header_height = line*2+17
    comparison_height = line*3+8 if len(pins) > 1 else 0
    footer_height = line+12
    panel_width = min(round(430*scale), max(320, int(width*.65)), width-24)
    max_height = height-20
    content_height = len(pins)*row_height+comparison_height
    panel_height = min(max_height, header_height+content_height+footer_height)
    x, y = position if position else (width-panel_width-12, 10)
    x, y = int(max(8, min(width-panel_width-8, x))), int(max(8, min(height-panel_height-8, y)))
    box = (x, y, x+panel_width, y+panel_height)
    scene.inspector = box
    # This is a live blur of our own graph's real pixels, with a translucent black tint.
    crop = image.crop(box).filter(ImageFilter.GaussianBlur(10)).convert("RGBA")
    tint = Image.new("RGBA", crop.size, (8, 12, 19, 184))
    glass = Image.alpha_composite(crop, tint).convert("RGB")
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, panel_width-1, panel_height-1), radius=12, fill=255)
    image.paste(glass, (x, y), mask)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=12, outline="#68788e", width=1)
    draw.text((x+14, y+10), f"Pinned samples · {len(pins)}", font=bold, fill=TEXT)
    draw.text((x+14, y+10+line), "Drag to move · right-click to release", font=small, fill=MUTED)
    body_height = max(1, panel_height-header_height-footer_height)
    scene.row_count = max(1, body_height//row_height)
    scene.scroll_max = max(0, content_height-body_height)
    scene.scroll_offset = min(max(0, row_offset), scene.scroll_max)
    body_top = y+header_height
    body = image.crop((x+1, body_top, x+panel_width-1, body_top+body_height))
    body_draw = ImageDraw.Draw(body)
    row_y = -scene.scroll_offset
    for pin in pins:
        row_box = (8, row_y, panel_width-10, row_y+row_height-2)
        if row_y+row_height-2 > 0 and row_y < body_height:
            scene.rows.append(((x+9, body_top+max(0, row_y), x+panel_width-9,
                                body_top+min(body_height, row_y+row_height-2)), pin.label))
        color = colors[pin.uuid]
        if active_pin == pin.label:
            body_draw.rounded_rectangle(row_box, radius=5, outline=color)
        reading = pin.reading
        stamp = datetime.fromtimestamp(pin.snapshot.wall_time).strftime("%H:%M:%S.%f")[:-3]
        body_draw.text((14, row_y+3), f"{pin.label}  ·  {names[pin.uuid]}  ·  {stamp}",
                  font=bold, fill=color)
        body_draw.text((14, row_y+3+line), f"Load {exact('utilization', reading.utilization)}%   |   VRAM {exact('memory', reading.memory)} GiB",
                  font=small, fill=TEXT)
        body_draw.text((14, row_y+3+line*2), f"Temp {exact('temperature', reading.temperature)} °C   |   Power {exact('power', reading.power)} W",
                  font=small, fill=TEXT)
        row_y += row_height
    if len(pins) > 1:
        first, last = pins[0], pins[-1]
        diffs = compare_pins(first, last)
        body_draw.line((14, row_y+3, panel_width-14, row_y+3), fill=GRID)
        body_draw.text((14, row_y+8), f"{first.label} → {last.label}  ·  Δt {diffs['seconds']:+.3f}s",
                  font=small, fill=MUTED)
        body_draw.text((14, row_y+8+line), f"ΔLoad {delta('utilization',diffs['utilization'])} pp   |   ΔVRAM {delta('memory',diffs['memory'])} GiB",
                  font=small, fill=TEXT)
        body_draw.text((14, row_y+8+line*2), f"ΔTemp {delta('temperature',diffs['temperature'])} °C   |   ΔPower {delta('power',diffs['power'])} W",
                  font=small, fill=TEXT)
    image.paste(body, (x+1, body_top))
    footer = "Scroll inside for samples and comparisons" if scene.scroll_max else "Recorded samples · all four metrics cross-referenced"
    draw.text((x+15, y+panel_height-footer_height+4), footer, fill=MUTED, font=small)
