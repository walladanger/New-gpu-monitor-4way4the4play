import time
from unittest.mock import patch
import unittest

from gpu_data import Reading,Snapshot
from graph_scene import render_graph


def readings(now=None):
    now=time.monotonic() if now is None else now
    return [Snapshot(now-1,time.time()-1,(Reading('0','GPU-A','NVIDIA GeForce RTX 3090',0,1,24,40,10,310),)),
            Snapshot(now,time.time(),(Reading('0','GPU-A','NVIDIA GeForce RTX 3090',100,2,24,42,200,310),))]


class InteractionRegressionTests(unittest.TestCase):
    def test_click_on_visible_segment_selects_an_actual_sample(self):
        history=readings()
        scene=render_graph('utilization',600,400,history,{'GPU-A':history[-1].readings[0]},
                           {'GPU-A':'#70A9FF'},None,2,history[-1].stamp)
        a,b=scene.points
        point=scene.nearest((a.x+b.x)/2,(a.y+b.y)/2)
        self.assertIsNotNone(point,'Clicking the visible line between sparse samples must work')
        self.assertIn(point.snapshot,history,'Selection must remain an actual recorded sample')

    def test_refresh_does_not_unmap_gpu_buttons(self):
        from dashboard import Dashboard
        app=Dashboard(collect=False)
        try:
            for snapshot in readings(): app.accept(snapshot)
            app.update();app.layout_graphs();app.update();app.redraw();app.update()
            button=app.charts[0].value_labels['GPU-A']
            unmaps=[]
            button.bind('<Unmap>',lambda event:unmaps.append(event))
            for _ in range(3):
                app.redraw();app.update()
            self.assertEqual(unmaps,[],'A refresh must not cancel an in-progress button click')
        finally:
            app.close()

    def test_expensive_graph_drawing_does_not_block_input_thread(self):
        import dashboard
        app=dashboard.Dashboard(collect=False)
        app.async_render=True
        try:
            for snapshot in readings(): app.accept(snapshot)
            app.update();app.layout_graphs();app.update()
            original=dashboard.render_graph
            def slow(*args,**kwargs):
                time.sleep(.15)
                return original(*args,**kwargs)
            with patch('dashboard.render_graph',side_effect=slow):
                before=time.monotonic()
                app.redraw()
                elapsed=time.monotonic()-before
                self.assertLess(elapsed,.12,'Graph drawing must leave the Tk event loop available')
        finally:
            app.close()

    def test_button_press_refresh_release_and_pin_work_while_rendering(self):
        import dashboard
        from types import SimpleNamespace
        app=dashboard.Dashboard(collect=False,async_render=True)
        try:
            for snapshot in readings(): app.accept(snapshot)
            app.update();app.layout_graphs();app.update();app.redraw();app.wait_for_renders()
            chart=app.charts[0];control=chart.value_labels['GPU-A']
            point=chart.scene.points[-1]
            original=dashboard.render_graph
            def slow(*args,**kwargs):
                time.sleep(.15)
                return original(*args,**kwargs)
            with patch('dashboard.render_graph',side_effect=slow):
                control.event_generate('<Enter>',x=10,y=10)
                control.event_generate('<ButtonPress-1>',x=10,y=10)
                app.redraw();app.update()
                control.event_generate('<ButtonRelease-1>',x=10,y=10)
                app.update()
                self.assertEqual(chart.focused_uuid,'GPU-A')
                self.assertIsNotNone(app.glass_popup)
                app.glass_popup.close()
                before=time.monotonic()
                chart.left_click(SimpleNamespace(x=point.x,y=point.y))
                self.assertLess(time.monotonic()-before,.12)
                self.assertTrue(chart.pins.pins)
                app.wait_for_renders()
                self.assertTrue(chart.scene.rows)
        finally:
            app.close()
