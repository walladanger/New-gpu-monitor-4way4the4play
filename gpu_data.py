"""NVIDIA sampling and immutable records shared by every graph window."""
from __future__ import annotations

import csv
import io
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

FIELDS = "index,uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit"
METRICS = (("utilization", "GPU usage", "%"), ("memory", "VRAM used", "GiB"),
           ("temperature", "Temperature", "\u00b0C"), ("power", "Board power", "W"))


def number(value: str) -> float | None:
    try:
        result = float(value.strip())
        return result if math.isfinite(result) and result >= 0 else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Reading:
    index: str
    uuid: str
    name: str
    utilization: float | None
    memory: float | None
    capacity: float | None
    temperature: float | None
    power: float | None
    power_limit: float | None


@dataclass(frozen=True)
class Snapshot:
    stamp: float
    wall_time: float
    readings: tuple[Reading, ...]

    def gpu(self, uuid: str) -> Reading | None:
        return next((reading for reading in self.readings if reading.uuid == uuid), None)


@dataclass(frozen=True)
class Pin:
    label: str
    snapshot: Snapshot
    uuid: str

    @property
    def reading(self) -> Reading:
        reading = self.snapshot.gpu(self.uuid)
        if reading is None:
            raise ValueError("A pin must refer to a GPU in its recorded snapshot.")
        return reading


class PinStore:
    def __init__(self):
        self.pins: list[Pin] = []
        self.serial = 0

    def add(self, snapshot: Snapshot, uuid: str) -> Pin:
        if snapshot.gpu(uuid) is None:
            raise ValueError("Cannot pin a GPU absent from this sample.")
        for pin in self.pins:
            if pin.snapshot.stamp == snapshot.stamp and pin.uuid == uuid:
                return pin
        self.serial += 1
        label = chr(64 + self.serial) if self.serial <= 26 else f"P{self.serial}"
        pin = Pin(label, snapshot, uuid)
        self.pins.append(pin)
        return pin

    def expire(self, now: float, seconds: int):
        self.pins[:] = [pin for pin in self.pins if pin.snapshot.stamp >= now - seconds]

    def remove(self, label: str):
        self.pins[:] = [pin for pin in self.pins if pin.label != label]

    def copy(self) -> PinStore:
        result = PinStore()
        result.pins = self.pins.copy()
        result.serial = self.serial
        return result


def compare_pins(first: Pin, last: Pin) -> dict[str, float | None]:
    result = {"seconds": last.snapshot.stamp - first.snapshot.stamp}
    for key, _, _ in METRICS:
        a, b = getattr(first.reading, key), getattr(last.reading, key)
        result[key] = None if a is None or b is None else b - a
    return result


def panel_columns(width: int) -> int:
    return 1 if width < 1060 else 2


def gpu_labels(devices: dict[str, Reading]) -> dict[str, str]:
    """Readable names; ordinal suffixes distinguish otherwise identical cards."""
    names = {uuid: reading.name.removeprefix("NVIDIA GeForce ").removeprefix("NVIDIA ")
             for uuid, reading in devices.items()}
    labels, counts = {}, {}
    for uuid, name in names.items():
        counts[name] = counts.get(name, 0) + 1
        labels[uuid] = f"{name} #{counts[name]}" if list(names.values()).count(name) > 1 else name
    return labels


def parse_readings(output: str) -> list[Reading]:
    readings = []
    for row in csv.reader(io.StringIO(output)):
        if not row or not any(part.strip() for part in row):
            continue
        if len(row) != 9:
            raise ValueError("The NVIDIA driver returned an unexpected data format.")
        index, uuid, name = (part.strip() for part in row[:3])
        if not index.isdigit() or not uuid.startswith("GPU-"):
            raise ValueError("The NVIDIA driver returned an invalid GPU identity.")
        utilization, used, total, temperature, power, limit = map(number, row[3:])
        readings.append(Reading(index, uuid, name, utilization,
                                None if used is None else used / 1024,
                                None if total is None else total / 1024,
                                temperature, power, limit))
    if not readings:
        raise ValueError("No NVIDIA GPUs were reported by the driver.")
    return readings


def find_nvidia_smi() -> str:
    executable = shutil.which("nvidia-smi")
    if executable:
        return executable
    for candidate in (Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/nvidia-smi.exe",
                      Path(os.environ.get("ProgramFiles", r"C:\Program Files")) /
                      "NVIDIA Corporation/NVSMI/nvidia-smi.exe"):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("nvidia-smi was not found. Install a current NVIDIA graphics driver.")


def sample() -> list[Reading]:
    result = subprocess.run(
        [find_nvidia_smi(), f"--query-gpu={FIELDS}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[:250] or "NVIDIA driver query failed.")
    return parse_readings(result.stdout)


class Collector:
    def __init__(self):
        self.messages: queue.Queue = queue.Queue(maxsize=4)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="GPU metrics")
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                readings, error = sample(), None
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                readings, error = [], str(exc)
            snapshot = Snapshot(time.monotonic(), time.time(), tuple(readings))
            try:
                self.messages.put_nowait((snapshot, error))
            except queue.Full:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    pass
                self.messages.put_nowait((snapshot, error))
            self.stop.wait(max(0.05, 1 - (time.monotonic() - started)))
