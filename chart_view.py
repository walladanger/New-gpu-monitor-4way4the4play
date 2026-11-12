"""Per-graph time viewport and series appearance, independent of sampling."""
from dataclasses import dataclass
import re

LINE_STYLES = ("Line", "Filled", "Gradient", "Dashed", "Hatched")


def normalize_color(value):
    value = value.strip().removeprefix("#")
    if not re.fullmatch(r"(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value):
        raise ValueError("Use #RRGGBB or #RGB.")
    if len(value) == 3:
        value = "".join(character*2 for character in value)
    return "#"+value.upper()


@dataclass
class TimeView:
    zoom: float = 1.0
    lag: float = 0.0

    def bounds(self, base_seconds, now):
        self.zoom = max(1.0, min(max(1, base_seconds/2), self.zoom))
        span = base_seconds/self.zoom
        self.lag = max(0.0, min(base_seconds-span, self.lag))
        return now-self.lag-span, now-self.lag

    def zoom_by(self, factor, base_seconds, now, anchor=.5):
        left, right = self.bounds(base_seconds, now)
        anchor = max(0.0, min(1.0, anchor))
        moment = left+(right-left)*anchor
        self.zoom = max(1.0, min(base_seconds/2, self.zoom*factor))
        span = base_seconds/self.zoom
        self.lag = now-(moment+span*(1-anchor))
        self.bounds(base_seconds, now)

    def fractions(self, base_seconds):
        span = base_seconds/self.zoom
        left = (base_seconds-span-self.lag)/base_seconds
        return max(0, left), min(1, left+1/self.zoom)

    def pan_to(self, fraction, base_seconds, now):
        span = base_seconds/self.zoom
        self.lag = base_seconds-span-fraction*base_seconds
        self.bounds(base_seconds, now)

    def reset(self):
        self.zoom, self.lag = 1.0, 0.0
