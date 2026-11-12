import time
import unittest

from gpu_data import Reading, Snapshot, PinStore, compare_pins, gpu_labels, panel_columns, parse_readings
from PIL import Image, ImageDraw
from graph_scene import COLORS, Scene, paint_inspector, render_graph


def reading(uuid="GPU-a", index="0", power=100.25, memory=12.125):
    return Reading(index, uuid, "NVIDIA GeForce RTX 3090", 75, memory, 24, 60.25, power, 310)


class DataTests(unittest.TestCase):
    def test_unavailable_is_not_zero(self):
        gpu = parse_readings("0,GPU-a,RTX 3090,0,1024,24576,N/A,[Not Supported],310")[0]
        self.assertEqual(gpu.utilization, 0)
        self.assertEqual(gpu.memory, 1)
        self.assertEqual(gpu.capacity, 24)
        self.assertIsNone(gpu.temperature)
        self.assertIsNone(gpu.power)

    def test_identical_card_names_are_distinct(self):
        devices = {"GPU-a": reading(), "GPU-b": reading("GPU-b", "1")}
        self.assertEqual(list(gpu_labels(devices).values()), ["RTX 3090 #1", "RTX 3090 #2"])

    def test_pins_use_recorded_sample_and_only_expire_offscreen(self):
        records = [Snapshot(stamp, 1000+stamp, (reading(power=stamp),)) for stamp in (10, 20, 30)]
        store = PinStore()
        pins = [store.add(record, "GPU-a") for record in records]
        self.assertIs(store.add(records[0], "GPU-a"), pins[0])
        self.assertEqual(len(store.pins), 3)
        store.expire(70, 60)
        self.assertEqual(len(store.pins), 3)  # Boundary is still on screen.
        store.expire(70.01, 60)
        self.assertEqual([pin.label for pin in store.pins], ["B", "C"])
        store.remove("B")
        self.assertEqual(store.pins[0].reading.power, 30)

    def test_comparison_preserves_precision_and_missing_data(self):
        store = PinStore()
        a = store.add(Snapshot(1, 100, (reading(power=None),)), "GPU-a")
        b = store.add(Snapshot(2.125, 101, (reading(power=125.75, memory=12.1259765625),)), "GPU-a")
        diff = compare_pins(a, b)
        self.assertIsNone(diff["power"])
        self.assertEqual(diff["memory"], 1/1024)
        self.assertEqual(diff["seconds"], 1.125)

    def test_popout_pin_store_is_independent(self):
        store = PinStore()
        store.add(Snapshot(1, 100, (reading(),)), "GPU-a")
        clone = store.copy()
        clone.remove("A")
        self.assertEqual(len(store.pins), 1)
        self.assertFalse(clone.pins)

    def test_breakpoint(self):
        self.assertEqual(panel_columns(500), 1)
        self.assertEqual(panel_columns(1059), 1)
        self.assertEqual(panel_columns(1060), 2)


class PaintingTests(unittest.TestCase):
    def setUp(self):
        self.history = [Snapshot(stamp, 1000+stamp, (reading(power=100+stamp),)) for stamp in range(1, 61)]
        self.devices = {"GPU-a": self.history[-1].readings[0]}
        self.colors = {"GPU-a": COLORS[0]}

    def draw(self, width=620, height=260, pins=(), offset=0):
        return render_graph("power", width, height, self.history, self.devices, self.colors,
                            None, 60, 61, pins, row_offset=offset)

    def test_hit_test_returns_real_sample_not_interpolation(self):
        scene = self.draw()
        point = scene.points[25]
        hit = scene.nearest(point.x+1, point.y+1)
        self.assertIs(hit.snapshot, point.snapshot)
        self.assertIsNone(scene.nearest(0, 0))

    def test_multiple_pins_scroll_and_have_removable_rows(self):
        store = PinStore()
        for snapshot in self.history[::10]:
            store.add(snapshot, "GPU-a")
        for width, height in ((380, 180), (620, 260), (1100, 650)):
            with self.subTest(size=(width, height)):
                scene = self.draw(width, height, store.pins)
                self.assertEqual(len(scene.markers), 12)
                self.assertIsNotNone(scene.inspector)
                for (left, top, right, bottom), label in scene.rows:
                    self.assertEqual(scene.pin_at((left+right)/2, (top+bottom)/2), label)
                    self.assertGreaterEqual(top, scene.inspector[1])
                    self.assertLessEqual(bottom, scene.inspector[3])
                if height < 300:
                    self.assertGreater(scene.scroll_max, 0)
                    tail = self.draw(width, height, store.pins, 10**9)
                    self.assertEqual(tail.scroll_offset, tail.scroll_max)

    def test_inspector_is_composited_over_real_graph(self):
        store = PinStore()
        store.add(self.history[20], "GPU-a")
        scene = self.draw(pins=store.pins)
        raw = self.draw()
        self.assertNotEqual(scene.image.tobytes(), raw.image.tobytes())
        x1, y1, x2, y2 = scene.inspector
        # A known background gradient must remain visible through the blurred glass.
        image = Image.new("RGB", (620, 260))
        draw = ImageDraw.Draw(image)
        for x in range(620):
            draw.line((x, 0, x, 260), fill=(int(x/620*255), 100, 80))
        glass = Scene(image)
        paint_inspector(glass, store.pins, "power", self.colors, None, 0, None, 1, {"GPU-a": "RTX 3090"})
        left, top, right, bottom = glass.inspector
        a = glass.image.getpixel((left+30, top+5))
        b = glass.image.getpixel((right-30, top+5))
        self.assertGreater(b[0], a[0])

    def test_focusing_dims_other_lines_without_hiding_samples(self):
        second = reading("GPU-b", "1", power=270)
        history = [Snapshot(s.stamp, s.wall_time, s.readings+(second,)) for s in self.history]
        devices = {**self.devices, "GPU-b": second}
        colors = {**self.colors, "GPU-b": COLORS[1]}
        args = ("power", 620, 260, history, devices, colors, None, 60, 61)
        normal = render_graph(*args)
        focused = render_graph(*args, focused="GPU-a")
        self.assertEqual(len(normal.points), len(focused.points))
        self.assertNotEqual(normal.image.tobytes(), focused.image.tobytes())


if __name__ == "__main__":
    unittest.main()
