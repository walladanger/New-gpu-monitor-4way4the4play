import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from preferences import Preferences,validate
from window_chrome import fit_bounds
from gpu_data import Reading,Snapshot


def reading(uid,index='0',name='NVIDIA GeForce RTX 3090'):
    return Reading(index,uid,name,45,2,24,40,110,310)


class PreferenceTests(unittest.TestCase):
    def test_atomic_failure_preserves_original_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'preferences.json'
            preferences=Preferences(path)
            preferences.save({'schema':1,'main':{'history':'5 minutes'}})
            original=path.read_bytes()
            with patch.object(Path,'replace',side_effect=OSError('simulated write failure')):
                with self.assertRaises(OSError):
                    preferences.save({'schema':1,'main':{'history':'1 hour'}})
            self.assertEqual(path.read_bytes(),original)
            self.assertFalse(list(Path(temporary).glob('*.tmp')))

    def test_corrupt_backup_and_future_schema_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'preferences.json'
            path.write_text('{bad json',encoding='utf-8')
            preferences=Preferences(path)
            self.assertEqual(preferences.load(),{})
            preferences.save({'schema':1,'main':{}})
            backups=list(Path(temporary).glob('preferences-invalid-*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_text(),'{bad json')
            future='{"schema": 99, "keep": true}'
            path.write_text(future)
            preferences=Preferences(path)
            self.assertEqual(preferences.load(),{})
            self.assertFalse(preferences.save({'schema':1,'main':{}}))
            self.assertEqual(path.read_text(),future)

    def test_validation_and_offscreen_geometry(self):
        result=validate({'schema':1,'main':{'history':['invalid'],'bounds':[0,0,-500,0],
                         'charts':{'power':{'colors':{'GPU-A':'#abc','GPU-B':'wrong'},'styles':{'GPU-A':'Steps'},'zoom':float('inf')}}}})
        self.assertEqual(result['main']['history'],'1 minute')
        self.assertIsNone(result['main']['bounds'])
        self.assertEqual(result['main']['charts']['power']['colors'],{'GPU-A':'#AABBCC'})
        self.assertEqual(result['main']['charts']['power']['styles'],{})
        self.assertEqual(fit_bounds((9000,-4000,1600,1400),(0,0,1280,1000)),(0,0,1280,1000))
        self.assertEqual(fit_bounds((-1800,100,900,700),(-1920,0,0,1080)),(-1800,100,900,700))


class PreferenceDashboardTests(unittest.TestCase):
    def test_restart_restores_uuid_scoped_views_and_detached_windows(self):
        from dashboard import Dashboard
        with tempfile.TemporaryDirectory() as temporary:
            first=Dashboard(collect=False,preferences=True,data_dir=temporary)
            first.global_gpu_settings.set(False)
            first.update()
            first.accept(Snapshot(time.monotonic(),time.time(),(reading('GPU-A'),reading('GPU-B','1'))))
            first.gpu_choice.set('RTX 3090 #2')
            first.window_choice.set('1 hour')
            first.charts[0].series_colors['GPU-B']='#123456'
            first.charts[0].line_styles['GPU-B']='Hatched'
            first.charts[0].focused_uuid='GPU-B'
            first.charts[0].view.zoom=2
            window=first.open_window(first.charts[0])
            window.window_choice.set('5 minutes')
            window.gpu_choice.set('RTX 3090 #1')
            window.chart.series_colors['GPU-A']='#ABCDEF'
            first.update()
            first.close()
            second=Dashboard(collect=False,preferences=True,data_dir=temporary)
            try:
                self.assertEqual(second.window_choice.get(),'1 hour')
                self.assertEqual(len(second.detached),1)
                # Discovery order changes: restoration must still select B.
                second.accept(Snapshot(time.monotonic(),time.time(),(reading('GPU-B','0'),reading('GPU-A','1'))))
                self.assertEqual(second.selected_uuid(second.gpu_choice),'GPU-B')
                self.assertEqual(second.charts[0].series_colors['GPU-B'],'#123456')
                self.assertEqual(second.charts[0].line_styles['GPU-B'],'Hatched')
                self.assertEqual(second.charts[0].view.zoom,2)
                self.assertEqual(second.detached[0].window_choice.get(),'5 minutes')
                self.assertEqual(second.selected_uuid(second.detached[0].gpu_choice),'GPU-A')
                self.assertEqual(second.detached[0].chart.series_colors['GPU-A'],'#ABCDEF')
            finally:
                second.close()

    def test_duplicate_name_arrival_preserves_filter_and_manual_override(self):
        from dashboard import Dashboard
        app=Dashboard(collect=False)
        try:
            app.accept(Snapshot(time.monotonic(),time.time(),(reading('GPU-A'),)))
            app.gpu_choice.set('RTX 3090')
            app.accept(Snapshot(time.monotonic(),time.time(),(reading('GPU-A'),reading('GPU-B','1'))))
            self.assertEqual(app.selected_uuid(app.gpu_choice),'GPU-A')
            self.assertEqual(app.gpu_choice.get(),'RTX 3090 #1')
            app.pending_gpu='GPU-C'
            app.gpu_choice.set('All GPUs')
            app.filter_changed(app)
            app.accept(Snapshot(time.monotonic(),time.time(),(reading('GPU-C','2'),)))
            self.assertIsNone(app.selected_uuid(app.gpu_choice))
        finally:
            app.close()
