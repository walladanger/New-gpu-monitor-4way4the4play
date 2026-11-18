"""Regressions for read-only system metrics and the optional System tab."""
import time
from types import SimpleNamespace
import unittest

from system_data import SystemSampler, SystemSnapshot
from system_graph import render_system_graph, available_series
from system_view import SERIES_MODES


class FakeCounters:
    def __init__(self, read, write):
        self.read_bytes, self.write_bytes = read, write


class FakePsutil:
    def __init__(self):
        self.read, self.write = 10_000_000, 3_000_000

    def cpu_percent(self, interval=None, percpu=False):
        return [10.0, 80.0, 60.0, 30.0] if percpu else 45.0

    def cpu_freq(self, percpu=False):
        return SimpleNamespace(current=4350)

    def virtual_memory(self):
        gib = 1024**3
        return SimpleNamespace(total=32*gib, used=12*gib, available=20*gib, cached=3*gib, percent=37.5)

    def disk_partitions(self, all=False):
        return [SimpleNamespace(device="C:\\", mountpoint="C:\\", fstype="NTFS"),
                SimpleNamespace(device="D:\\", mountpoint="D:\\", fstype="NTFS")]

    def disk_usage(self, name):
        gib = 1024**3
        return (SimpleNamespace(total=1024*gib, used=256*gib, free=768*gib) if name == "C:\\"
                else SimpleNamespace(total=2048*gib, used=1024*gib, free=1024*gib))

    def disk_io_counters(self, perdisk=False):
        return ({"PhysicalDrive0": FakeCounters(self.read//2, self.write//2),
                 "PhysicalDrive1": FakeCounters(self.read//2, self.write//2)}
                if perdisk else FakeCounters(self.read, self.write))


class SystemSamplingTests(unittest.TestCase):
    def test_logical_cpu_ram_volumes_and_rate_units(self):
        api=FakePsutil()
        sampler=SystemSampler(api)
        first=sampler.sample(stamp=100.0, wall_time=1000.0)
        self.assertEqual(first.values["cpu:thread:3"], 30)
        self.assertEqual(first.values["cpu:total"], 45)
        self.assertEqual(first.values["cpu:clock"], 4.35)
        self.assertEqual(first.values["ram:used"], 12)
        self.assertEqual(first.values["ram:available"], 20)
        self.assertEqual(first.values["ram:used_pct"], 37.5)
        self.assertEqual(first.values["disk:volume:C:used"], 256)
        self.assertEqual(first.values["disk:volume:D:free"], 1024)
        self.assertIsNone(first.values["disk:total:read"], "First counter sample has no rate")
        api.read+=2_097_152
        api.write+=1_048_576
        second=sampler.sample(stamp=102.0, wall_time=1002.0)
        self.assertAlmostEqual(second.values["disk:total:read"], 1.0)
        self.assertAlmostEqual(second.values["disk:total:write"], .5)
        self.assertAlmostEqual(second.values["disk:physical:PhysicalDrive0:read"], .5)
        self.assertEqual(second.values["disk:volume:C:used"], 256)

    def test_nonmonotonic_or_reset_disk_counters_never_produce_negative_rates(self):
        api=FakePsutil()
        sampler=SystemSampler(api)
        sampler.sample(stamp=2.0,wall_time=1000)
        api.read=1
        api.write=1
        result=sampler.sample(stamp=3.0,wall_time=1001)
        self.assertIsNone(result.values["disk:total:read"])
        self.assertIsNone(result.values["disk:total:write"])
        self.assertIsNone(sampler.sample(stamp=3.0,wall_time=1001).values["disk:total:read"])

    def test_measurement_family_and_render_keep_selected_threads_distinct(self):
        self.assertIn("cpu_percent", SERIES_MODES["cpu"])
        self.assertIn("cpu_clock", SERIES_MODES["cpu"])
        now=time.monotonic()
        snapshots=tuple(SystemSnapshot(now-2+i,time.time()-2+i,{
            "cpu:thread:0": 10+i, "cpu:thread:1": 80-i, "cpu:total": 40+i
        }) for i in range(3))
        series=available_series("cpu_percent", snapshots)
        self.assertEqual(set(series),{"cpu:total","cpu:thread:0","cpu:thread:1"})
        picture=render_system_graph("cpu_percent",640,310,snapshots,
            ("cpu:thread:0","cpu:thread:1"),{"cpu:thread:0":"#FF3030","cpu:thread:1":"#30FF30"},
            {"cpu:thread:0":"Line","cpu:thread:1":"Dashed"},now,30)
        self.assertEqual(picture.size,(640,310))

    def test_empty_readings_do_not_crash_chart(self):
        chart=render_system_graph("disk_rate",600,300,(),(),{},{},time.monotonic(),60)
        self.assertEqual(chart.size,(600,300))


class SystemDashboardTests(unittest.TestCase):
    def test_system_tab_is_separate_and_supports_multi_series_and_style(self):
        from dashboard import Dashboard
        app=Dashboard(collect=False)
        try:
            app.show_system()
            app.update()
            self.assertEqual(app.active_tab,"system")
            self.assertEqual(set(app.system_panels),{"cpu","ram","disk"})
            now=time.monotonic()
            app.accept_system(SystemSnapshot(now,time.time(),{
                "cpu:total": 40,"cpu:thread:0": 10,"cpu:thread:1": 70,
                "ram:used": 10,"ram:available": 20,
                "disk:total:read": 3,"disk:total:write": 2
            }))
            cpu=app.system_panels["cpu"]
            cpu.set_selected(("cpu:thread:0","cpu:thread:1"))
            cpu.set_style("Dashed")
            self.assertEqual(cpu.selected,{"cpu:thread:0","cpu:thread:1"})
            self.assertEqual(cpu.style,"Dashed")
            app.redraw()
            app.update()
            self.assertTrue(cpu.canvas.winfo_exists())
            app.show_live()
            app.update()
            self.assertEqual(app.active_tab,"live")
            self.assertEqual(len(app.charts),4)
        finally:
            app.close()

if __name__=="__main__":
    unittest.main()
