"""Component-level Tk checks; no mouse control or other apps are accessed."""
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import os
import queue

from PIL import Image
from controls import DarkSelect, QuickMenu, SelectMenu, ExportMenu

from dashboard import Dashboard
from gpu_data import Reading, Snapshot


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.app = Dashboard(collect=False)
        self.errors = []
        self.app.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.now = time.monotonic()
        for index in range(60):
            readings = tuple(Reading(str(gpu), f"GPU-{gpu}", "NVIDIA GeForce RTX 3090" if gpu < 2 else "NVIDIA GeForce RTX 4070",
                                     60+gpu*10, 12+gpu, 24 if gpu<2 else 12, 50+index/20, 90+index+gpu*30, 310)
                             for gpu in range(3))
            self.app.accept(Snapshot(self.now-60+index, time.time()-60+index, readings))
        self.pump()

    def pump(self, duration=.25):
        end = time.monotonic()+duration
        while time.monotonic() < end:
            self.app.update()
            time.sleep(.01)
        self.app.redraw()

    def tearDown(self):
        self.app.close()
        self.assertFalse(self.errors)

    def test_resize_stacks_all_four_graphs_and_restores_grid(self):
        self.app.geometry("1180x820")
        self.pump()
        self.assertEqual(self.app.columns, 2)
        self.app.geometry("1000x800")
        self.pump()
        self.assertEqual(self.app.columns, 1)
        self.assertGreater(self.app.charts[0].winfo_width(),self.app.viewport.winfo_width()-30)
        self.app.geometry("500x800")
        self.pump()
        self.assertEqual(self.app.columns, 1)
        self.assertEqual([int(chart.grid_info()["row"]) for chart in self.app.charts], [0,1,2,3])
        self.assertGreater(int(self.app.viewport.cget("scrollregion").split()[-1]), self.app.viewport.winfo_height())
        self.app.geometry("1180x820")
        self.pump()
        self.assertEqual(self.app.columns, 2)

    @unittest.skipUnless(os.name=="nt", "Windows window manager test")
    def test_frameless_controls_preserve_minimize_maximize_restore(self):
        chrome = self.app.chrome
        self.assertTrue(chrome.native,chrome.error)
        self.assertEqual(chrome.client_insets(),(0,0,0,0))
        chrome.buttons['maximize'].invoke()
        self.pump()
        self.assertTrue(chrome.is_maximized())
        chrome.buttons['maximize'].invoke()
        self.pump()
        self.assertFalse(chrome.is_maximized())
        chrome.buttons['minimize'].invoke()
        self.pump()
        self.assertTrue(chrome.user.IsIconic(chrome.hwnd))
        chrome.restore()
        self.pump()
        self.assertFalse(chrome.user.IsIconic(chrome.hwnd))
        self.assertEqual(chrome.client_insets(),(0,0,0,0))

    def test_ambient_animation_preserves_recorded_data_and_pin_coordinates(self):
        chart = self.app.charts[0]
        self.app.ambient.animated = True
        self.app.ambient.paint(now=12)
        chart.refresh()
        points = [(p.x,p.y,p.snapshot,p.uuid) for p in chart.scene.points]
        first = chart.scene.image.getpixel((1,1))
        self.app.ambient.paint(now=60)
        chart.refresh()
        self.assertEqual(points,[(p.x,p.y,p.snapshot,p.uuid) for p in chart.scene.points])
        self.assertNotEqual(first,chart.scene.image.getpixel((1,1)))
        self.assertEqual(len(self.app.charts),4)

    def test_redraw_error_does_not_stop_live_updates(self):
        app=self.app
        app.collector=SimpleNamespace(messages=queue.Queue(),stop=SimpleNamespace(set=lambda:None))
        real_redraw=app.redraw
        def broken():
            raise RuntimeError('injected redraw failure')
        app.redraw=broken
        app.tick()
        self.assertEqual(len(self.errors),1)
        self.assertIsNotNone(app.tick_job)
        app.after_cancel(app.tick_job)
        app.tick_job=None
        self.errors.clear()
        app.redraw=real_redraw
        record=Snapshot(time.monotonic(),time.time(),tuple(app.devices.values()))
        app.collector.messages.put((record,None))
        app.tick()
        self.assertIs(app.history[-1],record)
        self.assertIsNotNone(app.tick_job)

    def test_name_buttons_toggle_per_graph_focus(self):
        chart = self.app.charts[0]
        chart.value_labels["GPU-1"].invoke()
        self.assertEqual(chart.focused_uuid, "GPU-1")
        self.assertIsNone(self.app.charts[1].focused_uuid)
        chart.value_labels["GPU-1"].invoke()
        self.assertIsNone(chart.focused_uuid)
        self.assertIn("RTX 3090 #2", chart.value_labels["GPU-1"].cget("text"))
        self.app.legend_labels["GPU-0"].invoke()
        self.assertTrue(all(c.focused_uuid=="GPU-0" for c in self.app.charts))

    def test_quick_menu_changes_only_the_clicked_graph(self):
        chart = self.app.charts[0]
        chart.value_labels["GPU-1"].invoke()
        menu = self.app.glass_popup
        self.assertIsInstance(menu, QuickMenu)
        self.assertEqual(menu.uuid, "GPU-1")
        menu.color_at(130)
        self.assertIn("GPU-1", chart.series_colors)
        self.assertFalse(self.app.charts[1].series_colors)
        left,top,right,bottom = menu.style_tiles["Filled"]
        menu.click(SimpleNamespace(x=(left+right)/2, y=(top+bottom)/2))
        self.assertEqual(chart.line_styles["GPU-1"], "Filled")
        self.assertFalse(self.app.charts[1].line_styles)
        menu.close()
        self.assertIsNone(self.app.glass_popup)

    def test_hex_field_edits_preview_validate_and_do_not_close_menu(self):
        chart = self.app.charts[0]
        chart.value_labels["GPU-1"].invoke()
        menu = self.app.glass_popup
        menu.outside(SimpleNamespace(widget=menu.hex_entry))
        self.assertFalse(menu.closed)
        menu.hex_value.set("#a1b2c3")
        menu.apply_hex()
        self.assertEqual(chart.series_color("GPU-1"), "#A1B2C3")
        self.assertEqual(menu.hex_value.get(), "#A1B2C3")
        menu.hex_value.set("#nope")
        menu.apply_hex()
        self.assertEqual(chart.series_color("GPU-1"), "#A1B2C3")
        self.assertIn("#RRGGBB", menu.status)
        menu.hex_value.set("abc")
        menu.apply_hex()
        self.assertEqual(menu.hex_value.get(), "#AABBCC")
        menu.color_at(50)
        self.assertEqual(menu.hex_value.get(), chart.series_color("GPU-1"))
        self.assertEqual(set(menu.style_tiles), {"Line","Filled","Gradient","Dashed","Hatched"})
        self.assertFalse(hasattr(menu, "format_tiles"))

    def test_main_export_menu_selects_graph_and_gpu(self):
        import csv
        menu = self.app.open_export()
        self.assertIsInstance(menu, ExportMenu)
        box = menu.chart_tiles[3]
        menu.click(SimpleNamespace(x=(box[0]+box[2])/2, y=(box[1]+box[3])/2))
        box = menu.gpu_tiles["GPU-2"]
        menu.click(SimpleNamespace(x=(box[0]+box[2])/2, y=(box[1]+box[3])/2))
        with tempfile.TemporaryDirectory() as directory:
            path = menu.export_selected("csv", directory)
            self.assertIn("power", path.name)
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertTrue(rows)
            self.assertTrue(all(row["gpu_name"]=="RTX 4070" for row in rows))
        self.assertIsNone(self.app.charts[0].focused_uuid)

    def test_mouse_zoom_has_conditional_timeline_and_reset(self):
        chart = self.app.charts[0]
        self.assertFalse(chart.time_scrollbar.winfo_manager())
        chart.wheel(SimpleNamespace(x=250, y=70, delta=120, state=0))
        self.pump()
        self.assertGreater(chart.view.zoom, 1)
        self.assertEqual(chart.time_scrollbar.winfo_manager(), "pack")
        chart.pan_time("moveto", 0)
        self.assertGreater(chart.view.lag, 0)
        chart.reset_zoom()
        self.pump()
        self.assertEqual(chart.view.zoom, 1)
        self.assertFalse(chart.time_scrollbar.winfo_manager())

    def test_dark_selector_commits_selection_and_closes(self):
        self.assertIsInstance(self.app.window_choice, DarkSelect)
        menu = SelectMenu(self.app.window_choice)
        menu.choose(1)
        self.assertEqual(self.app.window_choice.get(), "5 minutes")
        self.assertIsNone(self.app.glass_popup)
        self.assertEqual(self.app.charts[0].popout.cget("text"), "")

    def test_pin_remove_popout_pause_and_export(self):
        chart = self.app.charts[3]
        # Use a recent sample; the oldest one can expire while opening a window.
        point = next(p for p in reversed(chart.scene.points) if p.uuid=="GPU-1")
        chart.left_click(SimpleNamespace(x=point.x, y=point.y))
        self.assertEqual(len(chart.pins.pins), 1)
        self.assertIs(chart.pins.pins[0].snapshot, point.snapshot)
        window = self.app.open_window(chart)
        self.pump()
        self.assertEqual(len(self.app.charts), 4)
        self.assertEqual(len(window.chart.pins.pins), 1)
        self.assertIsNotNone(window.chart.scene)
        window.window_choice.set("15 minutes")
        self.assertEqual(self.app.window_choice.get(), "1 minute")
        window.close()
        self.assertFalse(self.app.detached)
        # Right-click a visible inspector row removes exactly that pin.
        (left, top, right, bottom), label = chart.scene.rows[0]
        chart.right_click(SimpleNamespace(x=(left+right)/2, y=(top+bottom)/2))
        self.assertFalse(chart.pins.pins)
        self.app.toggle_pause()
        frozen = self.app.context(self.app.gpu_choice, self.app.window_choice)[5]
        self.pump()
        self.assertEqual(self.app.context(self.app.gpu_choice, self.app.window_choice)[5], frozen)
        self.app.toggle_pause()
        image = chart.export_image()
        self.assertGreater(image.width, 100)
        self.assertGreater(image.height, 100)
        with tempfile.TemporaryDirectory(prefix="gpu-graphs-test-") as directory:
            self.app.save_images(self.app.charts, directory)
            saved = list(Path(directory).glob("*.png"))
            self.assertEqual(len(saved), 1)
            with Image.open(saved[0]) as exported:
                self.assertEqual(exported.format, "PNG")
                self.assertGreater(exported.width, image.width)


if __name__ == "__main__":
    unittest.main()
