from pathlib import Path
import tempfile
import time
import unittest
import queue
from types import SimpleNamespace

from dashboard import Dashboard
from system_data import SystemSnapshot,SystemSampler
from resource_analytics import gauge_limit,metric_unit,occupancy_bins
from resource_menu import ResourceMenu,ColorMenu
from resource_preferences import validate_resources


class ResourceControlTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.app=Dashboard(collect=False,preferences=True,data_dir=self.directory.name)
        self.now=time.monotonic()
        values={'cpu:total':35,'cpu:clock':4.2,'ram:used_pct':50,'ram:total':64,
                'disk:total:read':12,'disk:volume:C:used':100,'disk:volume:C:free':900,'disk:volume:C:total':1000}
        values.update({f'cpu:thread:{i}':float(i%100) for i in range(64)})
        self.app.accept_system(SystemSnapshot(self.now,time.time(),values))
        self.app.update();self.app.redraw()

    def tearDown(self):
        self.app.close();self.directory.cleanup()

    def test_long_sensor_menu_scrolls_and_keeps_multiple_selections(self):
        self.app.show_system();self.app.update();self.app.redraw()
        panel=self.app.system_panels['cpu']
        panel.sensor_button.invoke()
        menu=self.app.glass_popup
        self.assertIsInstance(menu,ResourceMenu)
        self.assertGreater(len(menu.items),menu.page_size)
        for _ in range(80):menu.scroll(1)
        index=next(i for i,row in enumerate(menu.items) if row['label']=='Logical CPU 64')
        menu.choose(index)
        self.assertIn('cpu:thread:63',panel.selected)
        self.assertIn('cpu:total',panel.selected)
        self.assertFalse(menu.closed)
        menu.close()

    def test_color_field_previews_valid_values_and_retains_last_valid_color(self):
        gauge=self.app.resource_overview.gauges[0]
        picker=ColorMenu(gauge.style_button,gauge.spec.color,gauge.set_color)
        picker.value.set('#aabbcc')
        self.assertEqual(gauge.spec.color,'#AABBCC')
        picker.value.set('#invalid')
        self.assertEqual(gauge.spec.color,'#AABBCC')
        picker.close()

    def test_resource_layout_and_sensor_appearance_survive_restart(self):
        gauge=self.app.resource_overview.gauges[0]
        gauge.set_metric('cpu:clock');gauge.set_style('Arc');gauge.set_color('#ABCDEF')
        self.app.resource_overview.set_collapsed(True)
        panel=self.app.system_panels['cpu']
        panel.accept(self.app.system_history)
        panel.set_selected(('cpu:thread:12',));panel.set_style('Hatched');panel.set_color('cpu:thread:12','#123456')
        self.app.toggle_live_detail('ram')
        self.app.resource_heatmap.metric='cpu:clock'
        self.app.resource_heatmap.set_window('15 minutes')
        self.app.resource_heatmap.set_expanded(True)
        self.app.save_preferences()
        self.app.close()
        self.app=Dashboard(collect=False,preferences=True,data_dir=self.directory.name)
        self.assertTrue(self.app.resource_overview.collapsed)
        gauge=self.app.resource_overview.gauges[0]
        self.assertEqual((gauge.spec.metric,gauge.spec.style,gauge.spec.color),('cpu:clock','Arc','#ABCDEF'))
        panel=self.app.system_panels['cpu']
        self.assertEqual(panel.selected,{'cpu:thread:12'})
        self.assertEqual(panel.colors['cpu:thread:12'],'#123456')
        self.assertEqual(panel.styles['cpu:thread:12'],'Hatched')
        self.assertTrue(self.app.detail_expanded['ram'])
        self.assertEqual(self.app.resource_heatmap.metric,'cpu:clock')
        self.assertEqual(self.app.resource_heatmap.range_name,'15 minutes')
        self.assertTrue(self.app.resource_heatmap.expanded)

    def test_sensor_mode_switch_preserves_explicit_thread_selection(self):
        panel=self.app.system_panels['cpu']
        panel.accept(self.app.system_history)
        panel.set_selected(('cpu:thread:12',))
        panel.change_mode('cpu_clock');panel.change_mode('cpu_percent')
        self.assertEqual(panel.selected,{'cpu:thread:12'})

    def test_pause_freezes_system_collection_and_rack_timeline(self):
        self.app.collector=SimpleNamespace(messages=queue.Queue(),stop=SimpleNamespace(set=lambda:None))
        self.app.system_collector=SimpleNamespace(messages=queue.Queue(),stop=SimpleNamespace(set=lambda:None))
        self.app.toggle_pause()
        before=len(self.app.system_history)
        self.app.system_collector.messages.put((SystemSnapshot(self.now+1,time.time(),{'cpu:total':99}),None))
        self.app.tick()
        self.assertEqual(len(self.app.system_history),before)
        self.app.show_system();self.app.refresh_status()
        self.assertIn('PAUSED',self.app.live.cget('text'))


class ResourceFidelityTests(unittest.TestCase):
    def test_recorded_system_values_cannot_change_after_sampling(self):
        values={'cpu:total':35}
        snapshot=SystemSnapshot(100,1000,values)
        values['cpu:total']=99
        self.assertEqual(snapshot.values['cpu:total'],35)
        with self.assertRaises(TypeError):
            snapshot.values['cpu:total']=1

    def test_capacity_gauges_use_installed_totals_and_capacity_units(self):
        h=(SystemSnapshot(100,1000,{'ram:used':32,'ram:total':64,'disk:volume:C:used':100,'disk:volume:C:total':1000}),)
        self.assertEqual(gauge_limit('ram:used',h),64)
        self.assertEqual(gauge_limit('disk:volume:C:used',h),1000)
        self.assertEqual(metric_unit('ram:total'),'GiB')

    def test_clock_heatmap_ignores_out_of_window_scale_outliers(self):
        h=(SystemSnapshot(1,1000,{'cpu:clock':1000}),SystemSnapshot(100,1100,{'cpu:clock':4.2}),SystemSnapshot(101,1101,{'cpu:clock':4.3}))
        bins,scale=occupancy_bins(h,'cpu:clock',101,30)
        self.assertEqual(scale,4.3)
        self.assertAlmostEqual(sum(map(sum,bins)),1)

    def test_returning_disk_rate_uses_its_own_elapsed_interval(self):
        from test_system_resources import FakePsutil
        api=FakePsutil();sampler=SystemSampler(api)
        sampler.sample(stamp=100,wall_time=1000)
        real_io=api.disk_io_counters
        api.disk_io_counters=lambda perdisk=False:{} if perdisk else real_io(False)
        sampler.sample(stamp=109,wall_time=1009)
        api.read+=10*1024**2
        api.disk_io_counters=real_io
        result=sampler.sample(stamp=110,wall_time=1010)
        self.assertAlmostEqual(result.values['disk:physical:PhysicalDrive0:read'],.5)
        self.assertEqual(result.values['disk:volume:C:total'],1024)

    def test_invalid_resource_settings_are_bounded_and_default_safely(self):
        result=validate_resources({'gauges':[{'metric':'cpu:thread:bad','style':'invalid','color':'oops'}],
                                   'heatmap':{'window':[]},'panels':{'cpu':{'mode':[],'selected':['cpu:thread:bad','cpu:thread:2'],'style':{}}}})
        self.assertEqual(result['gauges'][0]['metric'],'cpu:total')
        self.assertEqual(result['panels']['cpu']['selected'],['cpu:thread:2'])
        self.assertEqual(result['heatmap']['window'],'5 minutes')
