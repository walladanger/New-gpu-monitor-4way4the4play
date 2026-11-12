"""CSV and PDF exports of one GPU in the current graph's visible time range."""
import csv
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw

from gpu_data import METRICS, gpu_labels
from graph_scene import BG, PANEL, TEXT, MUTED, exact, font, render_graph


def visible_records(history, uuid, left, right):
    return tuple(snapshot for snapshot in history if left <= snapshot.stamp <= right and snapshot.gpu(uuid) is not None)


def export_csv(path, records, uuid, name):
    if not records:
        raise ValueError("No recorded samples in the visible range.")
    with Path(path).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("timestamp_local", "timestamp_utc", "gpu_name", "gpu_uuid", "load_percent",
                         "vram_used_gib", "vram_used_mib", "vram_total_gib", "temperature_c", "board_power_w", "power_limit_w"))
        for snapshot in records:
            r = snapshot.gpu(uuid)
            writer.writerow((datetime.fromtimestamp(snapshot.wall_time).astimezone().isoformat(timespec="milliseconds"),
                             datetime.fromtimestamp(snapshot.wall_time, timezone.utc).isoformat(timespec="milliseconds"),
                             name, uuid, r.utilization, r.memory, None if r.memory is None else r.memory*1024,
                             r.capacity, r.temperature, r.power, r.power_limit))


def export_pdf(path, records, uuid, key, devices, colors, line_styles, pins, left, right, clock_now):
    if not records:
        raise ValueError("No recorded samples in the visible range.")
    name = gpu_labels(devices)[uuid]
    title = next(title for metric,title,_ in METRICS if metric==key)
    width, height = 1280, 1700

    def page(caption):
        image = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(image)
        draw.text((55, 40), "GPU Live Graphs", font=font(32, True), fill=TEXT)
        draw.text((55, 92), f"{name} · {title} · {caption}", font=font(22, True), fill=colors[uuid])
        return image, draw

    first, draw = page("visible time range")
    a = datetime.fromtimestamp(records[0].wall_time).astimezone().isoformat(timespec="milliseconds")
    b = datetime.fromtimestamp(records[-1].wall_time).astimezone().isoformat(timespec="milliseconds")
    draw.text((55, 133), f"{a}  to  {b}", font=font(17), fill=MUTED)
    graph = render_graph(key, 1170, 510, records, devices, colors, uuid, right-left, right,
                         pins, focused=uuid, line_styles=line_styles, clock_now=clock_now)
    first.paste(graph.image, (55, 175))
    draw.text((55, 715), f"{len(records)} actual driver samples · no interpolated measurements", font=font(20, True), fill=TEXT)
    y = 765
    for metric, caption, unit in METRICS:
        values = [getattr(snapshot.gpu(uuid), metric) for snapshot in records]
        values = [value for value in values if value is not None]
        stats = "unavailable" if not values else (
            f"min {exact(metric,min(values))}  |  max {exact(metric,max(values))}  |  sample average {exact(metric,mean(values))} {unit}")
        draw.text((55, y), f"{caption}: {stats}", font=font(19), fill=TEXT)
        y += 39
    draw.text((55, y+25), "Raw readings for every visible sample follow on the next pages.", font=font(19), fill=MUTED)
    draw.text((55, y+65), "Source: NVIDIA driver / nvidia-smi. Board power is not wall-socket power.", font=font(17), fill=MUTED)
    draw.text((55, y+95), "Blank CSV fields and n/a PDF cells mean unavailable, not zero.", font=font(17), fill=MUTED)
    draw.text((55, y+125), "Each timestamp marks query completion; individual sensors may use different sampling intervals.", font=font(17), fill=MUTED)
    pages = [first]
    for offset in range(0, len(records), 51):
        image, draw = page(f"recorded samples {offset+1}–{min(offset+51,len(records))}")
        xs = (55, 340, 490, 740, 960)
        for x, caption in zip(xs, ("Local timestamp", "Load (%)", "VRAM (GiB)", "Temp (°C)", "Board power (W)")):
            draw.text((x, 155), caption, font=font(18, True), fill=MUTED)
        for index, snapshot in enumerate(records[offset:offset+51]):
            r = snapshot.gpu(uuid)
            values = (datetime.fromtimestamp(snapshot.wall_time).strftime("%H:%M:%S.%f")[:-3],
                      exact("utilization", r.utilization), exact("memory", r.memory),
                      exact("temperature", r.temperature), exact("power", r.power))
            y = 202+index*27
            if index%2 == 0:
                draw.rectangle((45, y-3, width-45, y+23), fill=PANEL)
            for x, value in zip(xs, values):
                draw.text((x, y), value.replace("unavailable", "n/a"), font=font(17), fill=TEXT)
        pages.append(image)
    for index, image in enumerate(pages):
        ImageDraw.Draw(image).text((width-55, height-55), f"{index+1} / {len(pages)}", font=font(17), fill=MUTED, anchor="rm")
    pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])
