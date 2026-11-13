from datetime import datetime
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest

from dashboard import Dashboard,WINDOWS
from gpu_data import Reading,Snapshot
from graph_scene import render_graph,time_axis
from preferences import validate


def history():
    now=time.monotonic()
    return tuple(Snapshot(now-9+i,time.time()-9+i,(Reading('0','GPU-A','NVIDIA GeForce RTX 3090',20+i,2,24,40,100,310),)) for i in range(10))


class GPUSettingsTests(unittest.TestCase):
    def setUp(self):
        self.app=Dashboard(collect=False)
        for record in history():
            self.app.accept(record)
        self.app.update();self.app.layout_graphs();self.app.update();self.app.redraw()

    def tearDown(self):
        self.app.close()

    def test_default_global_color_style_opacity_and_detached_propagation(self):
        self.assertTrue(self.app.global_gpu_settings.get())
        chart=self.app.charts[0]
        window=self.app.open_window(chart)
        chart.value_labels['GPU-A'].invoke()
        menu=self.app.glass_popup
        menu.hex_value.set('#ab1234')
        left,top,right,bottom=menu.style_tiles['Gradient']
        menu.click(SimpleNamespace(x=(left+right)/2,y=(top+bottom)/2))
        menu.opacity_at(16+(menu.width-32)*.6)
        for target in self.app.all_charts():
            self.assertEqual(target.series_color('GPU-A'),'#AB1234')
            self.assertEqual(target.line_styles['GPU-A'],'Gradient')
            self.assertAlmostEqual(target.series_opacity['GPU-A'],.4)
        window.close()

    def test_unchecked_changes_stay_local_then_reenable_unifies(self):
        a,b=self.app.charts[:2]
        self.app.apply_gpu_setting(a,'GPU-A','colors','#ABCDEF')
        self.app.global_gpu_settings.set(False)
        self.app.apply_gpu_setting(a,'GPU-A','colors','#123456')
        self.app.apply_gpu_setting(a,'GPU-A','opacity',.2)
        self.assertEqual(a.series_color('GPU-A'),'#123456')
        self.assertEqual(b.series_color('GPU-A'),'#ABCDEF')
        self.assertNotIn('GPU-A',b.series_opacity)
        self.app.global_gpu_settings.set(True)
        self.app.toggle_global_gpu_settings()
        self.assertTrue(all(c.series_color('GPU-A')=='#ABCDEF' for c in self.app.all_charts()))

    def test_slider_release_commits_outside_track_and_clamps(self):
        chart=self.app.charts[0]
        chart.value_labels['GPU-A'].invoke()
        menu=self.app.glass_popup
        menu.click(SimpleNamespace(x=20,y=300))
        menu.release(SimpleNamespace(x=menu.width+200,y=300))
        self.assertEqual(chart.series_opacity['GPU-A'],0)
        menu.click(SimpleNamespace(x=100,y=300))
        menu.release(SimpleNamespace(x=-200,y=300))
        self.assertEqual(chart.series_opacity['GPU-A'],1)
        self.assertFalse(menu.sliding)

    def test_clock_toggle_preserves_view_and_remains_per_window(self):
        chart=self.app.charts[0]
        chart.view.zoom=3;chart.view.lag=5
        chart.clock_button.invoke()
        self.assertEqual(chart.time_mode,'clock')
        self.assertEqual((chart.view.zoom,chart.view.lag),(3,5))
        self.assertEqual(self.app.charts[1].time_mode,'relative')
        window=self.app.open_window(chart)
        self.assertEqual(window.chart.time_mode,'clock')
        window.chart.clock_button.invoke()
        self.assertEqual(window.chart.time_mode,'relative')
        self.assertEqual(chart.time_mode,'clock')
        window.close()

    def test_global_controls_and_time_modes_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            from preferences import Preferences
            self.app.preferences=Preferences(Path(folder)/'preferences.json')
            self.app.apply_gpu_setting(self.app.charts[0],'GPU-A','colors','#AABBCC')
            self.app.apply_gpu_setting(self.app.charts[0],'GPU-A','opacity',.55)
            self.app.charts[0].time_mode='clock'
            self.app.window_choice.set('45 minutes')
            window=self.app.open_window(self.app.charts[1]);window.chart.time_mode='clock'
            self.app.save_preferences()
            restored=Dashboard(collect=False,preferences=True,data_dir=folder)
            try:
                self.assertTrue(restored.global_gpu_settings.get())
                for chart in restored.all_charts():
                    self.assertEqual(chart.series_color('GPU-A'),'#AABBCC')
                    self.assertEqual(chart.series_opacity['GPU-A'],.55)
                self.assertEqual(restored.charts[0].time_mode,'clock')
                self.assertEqual(restored.detached[0].chart.time_mode,'clock')
                self.assertEqual(restored.window_choice.get(),'45 minutes')
                restored.global_gpu_settings.set(False);restored.save_preferences()
            finally:
                restored.close()
            self.assertFalse(Preferences(Path(folder)/'preferences.json').load()['main']['global_gpu_settings'])
            # Avoid teardown overwriting the independently restored settings.
            self.app.preferences=None

    def test_extra_history_choices_validate_and_apply(self):
        for name,seconds in WINDOWS.items():
            self.app.window_choice.set(name)
            self.assertEqual(self.app.context(self.app.gpu_choice,self.app.window_choice)[4],seconds)
            self.assertEqual(validate({'schema':1,'main':{'history':name}})['main']['history'],name)
        self.assertEqual(set(WINDOWS.values()),{30,60,120,300,600,900,1800,2700,3600})


class ClockAndOpacityTests(unittest.TestCase):
    def test_aligned_clock_labels_use_recorded_wall_time_when_panned(self):
        wall=datetime(2026,11,13,10,32).timestamp()
        records=(Snapshot(100,wall,()),)
        labels=[label for _,label in time_axis(records,300,100,100,'clock')]
        self.assertIn('10:32 AM',labels)
        panned=[label for _,label in time_axis(records,300,40,100,'clock')]
        self.assertIn('10:31 AM',panned)
        self.assertNotIn('10:32 AM',panned)
        self.assertTrue(all('ago' not in label and not label.startswith('-') for label in panned))

    def test_clock_crossing_midnight_includes_dates(self):
        wall=datetime(2026,11,14,0,1).timestamp()
        labels=[label for _,label in time_axis((Snapshot(100,wall,()),),300,100,100,'clock')]
        self.assertTrue(any('Nov 13' in label for label in labels))
        self.assertTrue(any('Nov 14' in label for label in labels))

    def test_transparency_blends_series_without_dimming_grid(self):
        from PIL import Image
        records=history();devices={'GPU-A':records[-1].readings[0]}
        def draw(opacity):
            return render_graph('utilization',600,400,records,devices,{'GPU-A':'#FF0000'},None,30,records[-1].stamp,opacities={'GPU-A':opacity})
        full,half,empty=draw(1),draw(.5),draw(0)
        point=full.points[4];pixel=(int(point.x),int(point.y))
        expected=Image.blend(empty.image,full.image,.5).getpixel(pixel)
        self.assertEqual(half.image.getpixel(pixel),expected)
        self.assertEqual(half.image.getpixel((48,16)),full.image.getpixel((48,16)))
        self.assertFalse(empty.points)
        self.assertIsNone(empty.nearest(point.x,point.y))

    def test_validation_rejects_nonfinite_opacity_and_bad_time_mode(self):
        result=validate({'schema':1,'main':{'charts':{'power':{'opacity':{'A':.5,'B':float('nan'),'C':1.2,'D':False},'time_mode':'bad'}}}})
        view=result['main']['charts']['power']
        self.assertEqual(view['opacity'],{'A':.5})
        self.assertEqual(view['time_mode'],'relative')
