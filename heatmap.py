"""Time spent in measured GPU value bands over the visible chart range."""
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from math import ceil, floor, isfinite, log10

from PIL import Image, ImageDraw

from gpu_data import METRICS, gpu_labels
from graph_scene import GRID, MUTED, PANEL, TEXT, Scene, dim_color, font, time_axis
from resource_analytics import intensity_color

PALETTE = tuple(intensity_color(fraction) for fraction in (.01, .25, .55, .75, 1))
EMPTY = '#10151f'
MAX_GAP = 2.5  # Match the existing line chart's gap threshold for the 1 Hz sampler.


@dataclass
class HeatmapLane:
    name: str
    bounds: tuple[int, int, int, int]
    cells: dict[tuple[int, int], float]
    coverage: list[float]
    y_edges: tuple[int, ...]


@dataclass
class HeatmapScene(Scene):
    lanes: list[HeatmapLane] = field(default_factory=list)
    columns: int = 0
    rows_count: int = 0
    value_step: float = 0
    column_seconds: float = 0
    unit: str = ''
    x_edges: tuple[int, ...] = ()
    wall_start: float | None = None

    def cell_at(self, x, y):
        for lane in self.lanes:
            left, top, right, bottom = lane.bounds
            if left <= x < right and top <= y < bottom:
                column = bisect_right(self.x_edges, x) - 1
                y_index = bisect_right(lane.y_edges, y) - 1
                row = self.rows_count - 1 - y_index
                spent = lane.cells.get((column, row), 0)
                low, high = row * self.value_step, (row + 1) * self.value_step
                coverage = lane.coverage[column]
                duration = f'{spent:.2f}s estimated in band' if coverage else 'No measured interval'
                label = (f'{lane.name}  ·  {low:.5g}–{high:.5g} {self.unit}  ·  {duration}\n'
                         f'{coverage:.2f}s of {self.column_seconds:.2f}s covered in this time column')
                if self.wall_start is not None:
                    start = datetime.fromtimestamp(self.wall_start + column * self.column_seconds)
                    end = datetime.fromtimestamp(self.wall_start + (column + 1) * self.column_seconds)
                    label += f'\n{start.isoformat(sep=" ", timespec="milliseconds")} – {end:%H:%M:%S} local'
                x0, x1 = self.x_edges[column:column + 2]
                y0, y1 = lane.y_edges[y_index:y_index + 2]
                return (x0, y0, x1, y1), label
        return None


def bucket_intervals(history, key, ids, left, right, columns, rows, value_step):
    """Weight the previous valid reading by elapsed time, clipped to bin edges.

    Missing readings and gaps interrupt coverage. The final reading carries no
    duration until another observation establishes the end of its interval.
    """
    cells = {uid: {} for uid in ids}
    coverage = {uid: [0.0] * columns for uid in ids}
    span = (right - left) / columns
    if span <= 0:
        return cells, coverage
    previous = None
    for current in history:
        if previous is None:
            previous = current
            continue
        first = previous
        previous = current
        if current.stamp <= left or first.stamp >= right or not 0 < current.stamp - first.stamp <= MAX_GAP:
            continue
        start, end = max(left, first.stamp), min(right, current.stamp)
        values = ((reading.uuid, getattr(reading, key)) for reading in first.readings if reading.uuid in cells)
        for uid, value in values:
            if value is None or not isfinite(value) or value < 0:
                continue
            row = min(rows - 1, floor(value / value_step))
            first_column = max(0, floor((start - left) / span))
            last_column = min(columns - 1, ceil((end - left) / span) - 1)
            for column in range(first_column, last_column + 1):
                duration = min(end, left + (column + 1) * span) - max(start, left + column * span)
                if duration > 0:
                    coverage[uid][column] += duration
                    index = column, row
                    cells[uid][index] = cells[uid].get(index, 0) + duration
    return cells, coverage


def band_step(ceiling, target_rows):
    raw = ceiling / target_rows
    factor = 10 ** floor(log10(raw))
    return next(step * factor for step in (1, 2, 2.5, 5, 10) if step * factor >= raw)


def render_heatmap(key, width, height, history, devices, colors, selected, seconds, now, *,
                   text_scale=1, focused=(), clock_now=None, background=None, time_mode='relative'):
    image = background.copy() if background is not None else Image.new('RGB', (width, height), PANEL)
    label_font = font(round(11 * text_scale))
    heading_font = font(round(12 * text_scale), True)
    draw = ImageDraw.Draw(image)
    scene = HeatmapScene(image, unit=next(unit for metric, _, unit in METRICS if metric == key))
    ids = [uid for uid in devices if selected is None or selected == uid]
    if not ids:
        draw.text((width / 2, height / 2), 'Waiting for GPU readings', font=label_font, fill=MUTED, anchor='mm')
        return scene

    left, right = round(47 * text_scale), width - 12
    header, footer = round(19 * text_scale), round(42 * text_scale)
    lane_height = (height - footer) // len(ids) - header - 5
    if lane_height < 12 or right - left < 20:
        draw.text((width / 2, height / 2), 'Select one GPU or enlarge this panel', font=label_font, fill=MUTED, anchor='mm')
        return scene

    capacity_metric = {'memory': 'capacity', 'power': 'power_limit'}.get(key)
    ceiling = 100 if key in ('utilization', 'temperature', 'power') else 1
    if capacity_metric:
        ceiling = max(ceiling, *(getattr(devices[uid], capacity_metric) or 0 for uid in ids))
    selected_ids = set(ids)
    for sample in history:
        if now - seconds - MAX_GAP <= sample.stamp <= now:
            for reading in sample.readings:
                value = getattr(reading, key)
                if reading.uuid in selected_ids and value is not None and isfinite(value):
                    ceiling = max(ceiling, value)
    scene.value_step = band_step(ceiling, min(48, max(4, lane_height // 2)))
    scene.rows_count = ceil(ceiling / scene.value_step)
    scene.columns = min(120, max(1, ceil(seconds)), (right - left) // 3)
    scene.column_seconds = seconds / scene.columns
    scene.x_edges = tuple(left + round(column * (right - left) / scene.columns)
                          for column in range(scene.columns + 1))
    if history:
        scene.wall_start = history[-1].wall_time + (now - seconds - history[-1].stamp)
    cells, coverage = bucket_intervals(history, key, ids, now - seconds, now, scene.columns, scene.rows_count, scene.value_step)
    names = gpu_labels(devices)
    for index, uid in enumerate(ids):
        top = index * (lane_height + header + 5) + header
        bottom = top + lane_height
        y_edges = tuple(bottom - round(row * lane_height / scene.rows_count)
                        for row in range(scene.rows_count, -1, -1))
        color = colors[uid]
        if focused and uid not in focused:
            color = dim_color(color)
        draw.text((left, top - header / 2), names[uid], font=heading_font, fill=color, anchor='lm')
        draw.rectangle((left, top, right - 1, bottom - 1), fill=EMPTY)
        if not cells[uid]:
            draw.text(((left + right) / 2, (top + bottom) / 2), 'No measured intervals',
                      font=label_font, fill=MUTED, anchor='mm')
        for (column, row), duration in cells[uid].items():
            strength = min(1, duration / scene.column_seconds)
            x0, x1 = scene.x_edges[column:column + 2]
            y_index = scene.rows_count - 1 - row
            y0, y1 = y_edges[y_index:y_index + 2]
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=intensity_color(max(.01, round(strength, 2))))
        for column, measured in enumerate(coverage[uid]):
            x0, x1 = scene.x_edges[column:column + 2]
            shade = round(30 + 145 * min(1, measured / scene.column_seconds))
            draw.line((x0, bottom + 1, x1 - 1, bottom + 1), fill=(shade, shade, shade))
        ticks = (0, scene.rows_count // 2, scene.rows_count) if lane_height >= 45 else (0, scene.rows_count)
        for row in ticks:
            y = bottom - round(row * lane_height / scene.rows_count)
            draw.text((left - 6, y), f'{row * scene.value_step:g}', fill=MUTED, font=label_font, anchor='rm')
        draw.line((left - 1, top, left - 1, bottom), fill=GRID)
        scene.lanes.append(HeatmapLane(names[uid], (left, top, right, bottom), cells[uid], coverage[uid], y_edges))

    for fraction, label in time_axis(history, seconds, now, clock_now, time_mode):
        x = left + (right - left) * fraction
        draw.text((x, bottom + round(11 * text_scale)), label, fill=MUTED, font=label_font,
                  anchor='rm' if fraction > .94 else 'lm' if fraction < .06 else 'mm')
    legend_y = height - round(12 * text_scale)
    for index, color in enumerate(PALETTE):
        x = left + 9 * index
        draw.rectangle((x, legend_y - 4, x + 8, legend_y + 4), fill=color)
    caption = 'Less → more time in band · gray strip = coverage'
    if draw.textlength(caption, font=label_font) > right - left - 51:
        caption = 'Time in band'
    draw.text((left + 51, legend_y), caption, fill=TEXT, font=label_font, anchor='lm')
    return scene
