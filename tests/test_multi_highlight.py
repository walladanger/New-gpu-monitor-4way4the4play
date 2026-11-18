"""Multi-GPU highlight regression: retain each GPU's hue, allow several focuses."""
import tempfile
from pathlib import Path
import time
import unittest

from dashboard import Dashboard
from gpu_data import Reading, Snapshot
from graph_scene import dim_color, render_graph
from preferences import validate


class MultiGpuHighlightTests(unittest.TestCase):
    def test_dimming_retains_distinct_hues_rather_than_muting_to_gray(self):
        red = dim_color("#FF0000")
        green = dim_color("#00FF00")
        blue = dim_color("#0000FF")
        self.assertEqual(len({red, green, blue}), 3)
        for color, channel in ((red, 0), (green, 1), (blue, 2)):
            rgb = tuple(int(color[offset:offset+2], 16) for offset in (1, 3, 5))
            self.assertGreater(rgb[channel], max(v for i, v in enumerate(rgb) if i != channel))
            self.assertGreater(rgb[channel], 175, "Unselected trace should be only slightly dimmed")

    def test_graph_can_emphasize_two_cards_without_losing_the_third_trace(self):
        now = time.monotonic()
        names = ("GPU-A", "GPU-B", "GPU-C")
        colors = dict(zip(names, ("#FF3030", "#30FF30", "#3030FF")))
        records = []
        for index in range(3):
            readings = tuple(
                Reading(str(card), uuid, uuid, 20+card*25+index, 1, 24, 43, 130, 310)
                for card, uuid in enumerate(names)
            )
            records.append(Snapshot(now-2+index, time.time()-2+index, readings))
        devices = {r.uuid:r for r in records[-1].readings}
        baseline = render_graph("utilization", 700, 350, records, devices, colors, None, 30, now)
        one = render_graph("utilization", 700, 350, records, devices, colors, None, 30, now, focused={"GPU-A"})
        two = render_graph("utilization", 700, 350, records, devices, colors, None, 30, now, focused={"GPU-A", "GPU-C"})
        self.assertEqual({p.uuid for p in baseline.points}, set(names))
        self.assertEqual({p.uuid for p in one.points}, set(names))
        self.assertEqual({p.uuid for p in two.points}, set(names))
        self.assertNotEqual(one.image.tobytes(), two.image.tobytes())

    def test_highlighting_is_additive_global_by_default_and_local_when_disabled(self):
        app = Dashboard(collect=False)
        try:
            now = time.monotonic()
            readings = tuple(
                Reading(str(i), f"GPU-{i}", f"RTX 3090 #{i}", 25+i*10, 2, 24, 45, 115, 310)
                for i in range(3)
            )
            app.accept(Snapshot(now, time.time(), readings))
            app.update()
            app.layout_graphs()
            app.redraw()
            app.update()
            chart = app.charts[0]

            chart.focus_gpu("GPU-0")
            chart.focus_gpu("GPU-2")
            app.redraw()
            app.update()
            for target in app.all_charts():
                self.assertEqual(target.focus_set, {"GPU-0", "GPU-2"})
            self.assertEqual(chart.value_labels["GPU-0"].cget("fg"), chart.series_color("GPU-0"))
            self.assertEqual(chart.value_labels["GPU-2"].cget("fg"), chart.series_color("GPU-2"))
            self.assertNotEqual(chart.value_labels["GPU-1"].cget("fg"), "#858A96")
            self.assertNotEqual(chart.value_labels["GPU-1"].cget("fg"), chart.series_color("GPU-1"))

            chart.focus_gpu("GPU-0")
            self.assertEqual(chart.focus_set, {"GPU-2"})
            chart.focus_gpu("GPU-2")
            self.assertEqual(chart.focus_set, set())
            app.global_gpu_settings.set(False)
            chart.focus_gpu("GPU-1")
            self.assertEqual(chart.focus_set, {"GPU-1"})
            self.assertTrue(all(not other.focus_set for other in app.charts[1:]))
            app.show_replay()
            app.update()
            self.assertEqual(app.replay_charts[0].focus_set, set())
        finally:
            app.close()

    def test_multiselect_is_saved_and_old_single_selection_restores(self):
        result = validate({"schema": 1, "main": {"charts": {
            "utilization": {"focus_uuids": ["GPU-A", "GPU-C", "GPU-C", "", None]},
            "power": {"focus": "GPU-B"},
        }}})
        self.assertEqual(result["main"]["charts"]["utilization"]["focus_uuids"], ["GPU-A", "GPU-C"])
        self.assertEqual(result["main"]["charts"]["power"]["focus_uuids"], ["GPU-B"])


if __name__ == "__main__":
    unittest.main()
