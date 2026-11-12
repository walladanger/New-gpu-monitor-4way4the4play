import csv
from pathlib import Path
import tempfile
import unittest

from chart_view import TimeView, LINE_STYLES, normalize_color
from exporting import export_csv, export_pdf, visible_records
from gpu_data import Reading, Snapshot
from graph_scene import COLORS, render_graph


class ViewTests(unittest.TestCase):
    def test_hex_normalization_and_rejection(self):
        self.assertEqual(normalize_color(" ffbd69 "), "#FFBD69")
        self.assertEqual(normalize_color("#abc"), "#AABBCC")
        for invalid in ("", "#12", "#ggff00", "red", "#12345678"):
            with self.assertRaises(ValueError):
                normalize_color(invalid)

    def test_cursor_anchored_zoom_and_pan_bounds(self):
        view = TimeView()
        before = view.bounds(60, 100)
        moment = before[0]+(before[1]-before[0])*.25
        view.zoom_by(2, 60, 100, .25)
        left, right = view.bounds(60, 100)
        self.assertAlmostEqual(left+(right-left)*.25, moment)
        self.assertEqual(right-left, 30)
        self.assertLess(view.fractions(60)[1]-view.fractions(60)[0], 1)
        view.pan_to(1, 60, 100)
        self.assertEqual(view.bounds(60, 100), (70,100))
        view.pan_to(-1, 60, 100)
        self.assertEqual(view.bounds(60, 100), (40,70))
        view.reset()
        self.assertEqual(view.fractions(60), (0,1))

    def test_zoom_limits_preserve_at_least_two_seconds(self):
        view = TimeView()
        view.zoom_by(10**6, 60, 100)
        a,b = view.bounds(60, 100)
        self.assertEqual(b-a, 2)
        view.zoom_by(.000001, 60, 100)
        self.assertEqual(view.zoom, 1)
        self.assertEqual(view.lag, 0)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.records = tuple(Snapshot(index, 1800000000+index,
                             (Reading("0", "GPU-a", "NVIDIA GeForce RTX 3090", 0 if index==0 else 75,
                                      21+index/1024, 24, None, 100.25+index, 310),)) for index in range(60))
        self.devices = {"GPU-a": self.records[-1].readings[0]}
        self.colors = {"GPU-a": COLORS[0]}

    def test_csv_has_exact_raw_values_and_only_visible_samples(self):
        records = visible_records(self.records, "GPU-a", 0, 5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"data.csv"
            export_csv(path, records, "GPU-a", "RTX 3090")
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0]["load_percent"], "0")
            self.assertEqual(rows[0]["temperature_c"], "")
            self.assertEqual(float(rows[1]["vram_used_mib"]), 21*1024+1)
            self.assertTrue(rows[0]["timestamp_utc"].endswith("+00:00"))

    def test_pdf_contains_graph_summary_and_raw_sample_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"data.pdf"
            export_pdf(path, self.records, "GPU-a", "power", self.devices, self.colors, {}, (), 0, 59, 59)
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertIn(b"%%EOF", data[-100:])
            self.assertIn(b"/Count 3", data)

    def test_every_line_style_changes_visuals_without_changing_samples(self):
        images = []
        for kind in LINE_STYLES:
            scene = render_graph("power", 620, 260, self.records, self.devices, self.colors,
                                 None, 60, 60, line_styles={"GPU-a":kind})
            self.assertEqual(len(scene.points), 60)
            images.append(scene.image.tobytes())
        self.assertEqual(len(set(images)), len(LINE_STYLES))
