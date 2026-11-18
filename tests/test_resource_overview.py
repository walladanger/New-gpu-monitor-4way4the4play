"""Compact gauges and recorded-duration heatmap regression tests."""
import time
import unittest
import threading
from unittest.mock import patch

from system_data import SystemSnapshot
from resource_analytics import (occupancy_bins, intensity_color, render_occupancy,
                                render_gauge, metric_value, available_metrics, GaugeSpec)


def sample(stamp, **values):
    return SystemSnapshot(stamp, 1_800_000_000+stamp, values)


class ResourceAnalyticsTests(unittest.TestCase):
    def test_dials_and_heatmap_draw_off_the_input_thread(self):
        from dashboard import Dashboard
        import resource_overview
        app=Dashboard(collect=False,async_render=True)
        owner=threading.get_ident()
        called=[]
        def checked_draw(original,kind):
            def draw(*args,**kwargs):
                self.assertNotEqual(threading.get_ident(),owner,
                    'Resource painting must not block the Tk input thread')
                called.append(kind)
                return original(*args,**kwargs)
            return draw
        try:
            now=time.monotonic()
            app.accept_system(sample(now,**{'cpu:total':35,'cpu:clock':4.2,
                                           'ram:used_pct':40,'disk:total:read':12}))
            app.resource_heatmap.set_expanded(True)
            app.update();app.layout_graphs();app.update()
            # Invalidate cached dials so this drives the actual drawing path.
            for gauge in app.resource_overview.gauges:
                gauge._last_frame_key=None
            with patch('resource_overview.render_gauge',side_effect=checked_draw(resource_overview.render_gauge,'dial')), \
                 patch('resource_overview.render_occupancy',side_effect=checked_draw(resource_overview.render_occupancy,'heatmap')):
                app.redraw()
                app.wait_for_renders()
            self.assertIn('dial',called)
            self.assertIn('heatmap',called)
        finally:
            app.close()

    def test_occupancy_counts_elapsed_recorded_seconds_not_the_load_magnitude(self):
        history=(sample(100, **{"cpu:total": 30,"cpu:clock":4.2}),
                 sample(101, **{"cpu:total": 30,"cpu:clock":4.2}),
                 sample(102, **{"cpu:total": 30,"cpu:clock":4.2}),
                 sample(103, **{"cpu:total": 90,"cpu:clock":4.5}))
        bins, scale=occupancy_bins(history,"cpu:total",now=104,seconds=8,
                                  columns=2,bands=10)
        self.assertEqual(sum(map(sum,bins)),3)
        self.assertEqual(scale,100)
        self.assertEqual(sum(bins[3]),3)
        self.assertEqual(sum(bins[9]),0)
        self.assertGreater(sum(bins[3]),sum(bins[9]))

    def test_heatmap_skips_stale_gaps_and_missing_samples(self):
        history=(sample(100,**{"cpu:clock":4.0}),
                 sample(101,**{"cpu:clock":4.0}),
                 sample(115,**{"cpu:clock":5.0}),
                 sample(116,**{"cpu:clock":None}),
                 sample(117,**{"cpu:clock":5.0}))
        matrix,scale=occupancy_bins(history,"cpu:clock",now=117,seconds=30,
                                    columns=6,bands=10)
        self.assertAlmostEqual(sum(map(sum,matrix)),2)
        self.assertGreaterEqual(scale,5.0)

    def test_color_increases_from_yellow_to_red_to_purple(self):
        a,b,c=(intensity_color(v) for v in (.1,.5,1.0))
        self.assertNotEqual(a,b)
        self.assertNotEqual(b,c)
        # Peak occupancy is purple-dominant rather than red.
        rb=tuple(int(c[i:i+2],16) for i in (1,3,5))
        self.assertGreater(rb[2],rb[1])

    def test_rendered_gauges_and_heatmap_are_valid_on_all_modes(self):
        h=(sample(100,**{"cpu:total":25,"cpu:clock":4.25,"ram:used_pct":50,
                         "disk:total:read":64,"disk:total:write":4}),)
        keys=available_metrics(h)
        self.assertIn("cpu:total",keys)
        for style in ("Ring","Pie","Arc"):
            img=render_gauge(160,160,25,100,"25%","#56D6BE",style)
            self.assertEqual(img.size,(160,160))
        heat=render_occupancy(620,280,h,"cpu:total",now=100,seconds=60)
        self.assertEqual(heat.size,(620,280))
        self.assertEqual(metric_value("cpu:clock",h[-1]),(4.25,"GHz"))

    def test_live_overview_stays_below_gpu_graphs_and_collapses_to_numbers(self):
        from dashboard import Dashboard
        app=Dashboard(collect=False)
        try:
            now=time.monotonic()
            app.accept_system(sample(now,**{"cpu:total":25,"cpu:clock":4.25,
                                           "ram:used_pct":40,"disk:total:read":12}))
            app.update()
            self.assertEqual(len(app.charts),4)
            self.assertEqual(len(app.resource_overview.gauges),4)
            self.assertIs(app.resource_overview.master,app.grid_frame)
            self.assertTrue(app.resource_overview.gauges[0].numeric.winfo_exists())
            app.resource_overview.set_collapsed(True)
            app.update()
            self.assertTrue(app.resource_overview.collapsed)
            self.assertFalse(app.resource_overview.gauges[0].canvas.winfo_ismapped())
            self.assertTrue(app.resource_overview.gauges[0].numeric.winfo_ismapped())
            app.resource_overview.set_collapsed(False)
            app.update()
            self.assertTrue(app.resource_overview.gauges[0].canvas.winfo_ismapped())
            self.assertFalse(app.resource_heatmap.expanded)
            app.resource_heatmap.set_expanded(True)
            app.update()
            self.assertTrue(app.resource_heatmap.expanded)
        finally:
            app.close()


if __name__=="__main__":
    unittest.main()
