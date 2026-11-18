"""Deterministic playback of stored NVIDIA samples (never synthetic interpolation).

The recorder saves device samples and wall timestamps, not UI events. Replay
therefore preserves sensor values and their timing, but does not reconstruct
earlier selections, window layouts or video frames.
"""
from bisect import bisect_left, bisect_right
import math


class ReplayTrack:
    """A read-only, finite timeline. All timing is in the original recording."""

    def __init__(self, records=(), session=None):
        self.records = tuple(sorted(records, key=lambda sample: sample.wall_time))
        self.times = tuple(sample.wall_time for sample in self.records)
        self.session = session
        self.start = self.times[0] if self.times else 0.0
        self.end = self.times[-1] if self.times else 0.0
        self.position = self.start
        self.index = 0
        self.playing = False
        self.speed = 1.0
        self._last_clock = None
        self.devices = {}
        for sample in self.records:
            for reading in sample.readings:
                self.devices[reading.uuid] = reading

    @property
    def duration(self):
        return self.end - self.start

    @property
    def fraction(self):
        return 1.0 if self.records and self.duration == 0 else (
            (self.position - self.start) / self.duration if self.duration else 0.0
        )

    def current(self):
        return self.records[self.index] if self.records else None

    def play(self, now):
        if not self.records or self.duration == 0:
            self.playing = False
            return
        if self.position >= self.end:
            self.seek(0)
        self.playing = True
        self._last_clock = float(now)

    def pause(self):
        self.playing = False
        self._last_clock = None

    def seek(self, fraction):
        if not self.records:
            return
        if not isinstance(fraction, (int, float)) or not math.isfinite(fraction):
            raise ValueError("Replay position must be a finite number")
        self.pause()
        self.position = self.start + min(1.0, max(0.0, fraction)) * self.duration
        self.index = min(len(self.records) - 1, max(0, bisect_right(self.times, self.position) - 1))

    def advance(self, now):
        if not self.playing:
            return False
        delta = max(0.0, float(now) - self._last_clock)
        self._last_clock = float(now)
        old_position = self.position
        self.position = min(self.end, self.position + delta * self.speed)
        self.index = min(len(self.records) - 1, bisect_right(self.times, self.position) - 1)
        if self.position >= self.end:
            self.pause()
        return self.position != old_position

    @property
    def stamp(self):
        """Monotonic coordinate corresponding to the original wall-time cursor."""
        return self.records[0].stamp + (self.position - self.start) if self.records else 0.0

    def available(self):
        sample = self.current()
        if sample is None or self.position - sample.wall_time > 2.5:
            return frozenset()
        return frozenset(reading.uuid for reading in sample.readings)

    def history(self, seconds):
        """Return only recorded samples at or before the cursor in this window."""
        if not self.records:
            return ()
        left = bisect_left(self.times, self.position - seconds)
        right = bisect_right(self.times, self.position)
        return self.records[left:right]
