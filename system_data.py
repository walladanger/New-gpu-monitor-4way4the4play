"""Read-only CPU, memory and disk sampler; no calls into Tk from its worker.

CPU threads are *logical processor* utilization, not per-process thread usage.
On Windows psutil reports a system CPU clock, not reliable per-thread GHz.
Physical-disk throughput and logical-volume capacity are deliberately distinct.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import queue
import threading
import time
from typing import Mapping

GIB = float(1024 ** 3)
MIB = float(1024 ** 2)


@dataclass(frozen=True)
class SystemSnapshot:
    stamp: float
    wall_time: float
    values: Mapping[str, float | None]


def _nonnegative(value):
    try:
        v = float(value)
        return v if math.isfinite(v) and v >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _volume_id(device):
    # Windows roots are C:\, D:\; labels are never mapped to physical drives.
    return str(device).strip().rstrip("\\/").rstrip(":")


class SystemSampler:
    def __init__(self, api):
        self.api = api
        self.previous_stamp = None
        self.previous_io = {}

    def _rate(self, key, counter, stamp):
        try:
            read, write = int(counter.read_bytes), int(counter.write_bytes)
        except (AttributeError, ValueError, TypeError, OverflowError):
            return None, None
        previous = self.previous_io.get(key)
        self.previous_io[key] = (read, write)
        if previous is None or self.previous_stamp is None or stamp <= self.previous_stamp:
            return None, None
        interval = stamp - self.previous_stamp
        if read < previous[0] or write < previous[1]:
            return None, None
        return ((read-previous[0])/(interval*MIB),
                (write-previous[1])/(interval*MIB))

    def sample(self, stamp=None, wall_time=None):
        stamp = time.monotonic() if stamp is None else float(stamp)
        wall_time = time.time() if wall_time is None else float(wall_time)
        p = self.api
        values = {}

        # psutil.cpu_percent is primed by the worker; the first reading is not
        # treated as a meaningful new rate. Separate calls are nonblocking.
        try:
            per_cpu = p.cpu_percent(interval=None,percpu=True)
            for index, percent in enumerate(per_cpu):
                values[f"cpu:thread:{index}"] = _nonnegative(percent)
            values["cpu:total"] = _nonnegative(p.cpu_percent(interval=None,percpu=False))
        except (OSError, RuntimeError, ValueError):
            values["cpu:total"] = None

        try:
            clock = p.cpu_freq(percpu=False)
            current = _nonnegative(clock.current if clock else None)
            values["cpu:clock"] = current / 1000 if current is not None else None
        except (OSError, RuntimeError, AttributeError, ValueError):
            values["cpu:clock"] = None

        try:
            ram=p.virtual_memory()
            for key, attribute in (("ram:used","used"),("ram:available","available"),
                                   ("ram:cached","cached")):
                number=_nonnegative(getattr(ram,attribute,None))
                values[key]=number / GIB if number is not None else None
            values["ram:used_pct"]=_nonnegative(getattr(ram,"percent",None))
        except (OSError, RuntimeError, ValueError):
            values["ram:used_pct"]=None

        try:
            # Volumes describe filesystem capacity, NOT per-physical-drive I/O.
            volumes=set()
            for partition in p.disk_partitions(all=False):
                disk=_volume_id(partition.device)
                if not disk or disk in volumes:
                    continue
                volumes.add(disk)
                try:
                    usage=p.disk_usage(partition.mountpoint)
                except (OSError, PermissionError, ValueError):
                    continue
                for key,attribute in (("used","used"),("free","free")):
                    n=_nonnegative(getattr(usage,attribute,None))
                    values[f"disk:volume:{disk}:{key}"]=n/GIB if n is not None else None
        except (OSError, RuntimeError, ValueError):
            pass

        try:
            io=p.disk_io_counters(perdisk=False)
            read,write=self._rate("total",io,stamp)
            values["disk:total:read"]=read
            values["disk:total:write"]=write
        except (OSError, RuntimeError, ValueError):
            values["disk:total:read"]=values["disk:total:write"]=None
        try:
            for disk,io in (p.disk_io_counters(perdisk=True) or {}).items():
                if not disk:
                    continue
                read,write=self._rate("physical:"+disk,io,stamp)
                values[f"disk:physical:{disk}:read"]=read
                values[f"disk:physical:{disk}:write"]=write
        except (OSError, RuntimeError, ValueError):
            pass

        self.previous_stamp=stamp
        return SystemSnapshot(stamp,wall_time,values)


class SystemCollector:
    """Keep system sampling off Tk's input thread, and bound pending messages."""

    def __init__(self, api=None):
        if api is None:
            import psutil
            api = psutil
        self.sampler=SystemSampler(api)
        self.messages=queue.Queue(maxsize=4)
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True,name="System resources")
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            started=time.monotonic()
            try:
                snapshot=self.sampler.sample()
                event=(snapshot,None)
            except (OSError,RuntimeError,ValueError) as error:
                event=(None,str(error))
            try:
                self.messages.put_nowait(event)
            except queue.Full:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    pass
                self.messages.put_nowait(event)
            self.stop.wait(max(.05,1-(time.monotonic()-started)))
