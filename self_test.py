"""Source/frozen smoke test. No NVIDIA query or personal settings are used."""
import json
from pathlib import Path
import tempfile
import time
import traceback

from version import VERSION


def run(report_path):
    from dashboard import Dashboard
    from gpu_data import Reading,Snapshot
    result={'version':VERSION,'success':False,'checks':[]}
    app=None
    session=tempfile.TemporaryDirectory()
    try:
        errors=[]
        app=Dashboard(collect=False,persist=True,preferences=True,data_dir=session.name,async_render=True)
        assert app.store.ready.wait(5)
        app.poll_history()
        app.report_callback_exception=lambda *args:errors.append(str(args[1]))
        now=time.monotonic()
        for i in range(30):
            app.accept(Snapshot(now-29+i,time.time()-29+i,(Reading('0','GPU-SELF-TEST','NVIDIA GeForce RTX 3090',float(i),2.5,24,42.5,100.25,310),)))
        app.paused=True;app.frozen_at=now
        for _ in range(5):
            app.update();time.sleep(.05)
        app.redraw();app.update();app.wait_for_renders()
        assert len(app.charts)==4 and all(c.scene for c in app.charts)
        result['checks'].append('four charts rendered')
        settings=app.open_settings()
        assert settings.info['path'].exists()
        settings.close()
        result['checks'].append('startup session log and dashboard settings')
        assert app.chrome.native
        original=app.chrome.bounds()
        app.chrome.toggle_maximize();app.update()
        app.chrome.toggle_maximize();app.update()
        assert app.chrome.bounds()[2:]==original[2:]
        result['checks'].append('frameless maximize/restore')
        app.charts[0].pins.add(app.history[-5],'GPU-SELF-TEST')
        detached=app.open_window(app.charts[0]);app.update();app.redraw()
        app.wait_for_renders()
        assert len(detached.chart.pins.pins)==1
        detached.close()
        result['checks'].append('pin and detached window')
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for kind in ('csv','pdf'):
                app.charts[0].export_series('GPU-SELF-TEST',kind,folder)
            app.save_images(app.charts,folder)
            assert {p.suffix for p in folder.iterdir()}=={'.csv','.pdf','.png'}
        result['checks'].append('CSV/PDF/PNG exports')
        assert not errors,errors
        app.apply_gpu_setting(app.charts[0],'GPU-SELF-TEST','colors','#123456')
        app.apply_gpu_setting(app.charts[0],'GPU-SELF-TEST','opacity',.6)
        app.charts[0].toggle_time_mode()
        app.wait_for_renders()
        app.window_choice.set('1 hour')
        app.resource_overview.gauges[0].set_style('Arc')
        app.close()
        app=Dashboard(collect=False,persist=True,preferences=True,data_dir=session.name,async_render=True)
        assert app.store.ready.wait(5)
        app.poll_history()
        assert len(app.history)==30
        assert app.available==set() and app.latest_at is None
        assert app.charts[0].series_colors['GPU-SELF-TEST']=='#123456'
        assert all(c.series_opacity['GPU-SELF-TEST']==.6 for c in app.charts)
        assert app.charts[0].time_mode=='clock'
        assert app.window_choice.get()=='1 hour'
        assert app.resource_overview.gauges[0].spec.style=='Arc'
        result['checks'].append('SQLite history and preferences survive restart')
        app.show_replay()
        deadline=time.monotonic()+8
        while (app.replay_loading or app.replay_track is None) and time.monotonic()<deadline:
            app.poll_history()
            app.update()
            time.sleep(.02)
        assert app.replay_track is not None and len(app.replay_track.records)==30
        assert app.replay_track.current().readings[0].utilization==0.0
        app.replay_end()
        assert app.replay_track.current().readings[0].utilization==29.0
        assert not app.replay_track.playing
        app.show_live()
        app.update()
        assert app.active_tab=='live'
        result['checks'].append('Replay tab loads last archived session, reaches final exact sample and returns to Live')
        # Import and exercise the real psutil extension in the frozen package.
        import psutil
        from system_data import SystemSampler,SystemSnapshot
        real_system=SystemSampler(psutil).sample()
        assert real_system.values['ram:total']>0
        assert any(key.startswith('cpu:thread:') for key in real_system.values)
        now=time.monotonic()
        for index in range(30):
            app.accept_system(SystemSnapshot(now-29+index,time.time()-29+index,
                {'cpu:total':float(index),'cpu:clock':4.2,'cpu:thread:0':float(index),
                 'ram:used_pct':50,'ram:used':32,'ram:total':64,'ram:available':32,
                 'disk:total:read':12,'disk:total:write':3}))
        app.show_system();app.update();app.redraw();app.wait_for_renders()
        assert all(panel.photo is not None for panel in app.system_panels.values())
        app.show_live();app.update()
        app.resource_heatmap.set_expanded(True)
        app.update();app.layout_graphs();app.update();app.redraw();app.wait_for_renders()
        assert all(gauge.photo is not None for gauge in app.resource_overview.gauges)
        assert app.resource_heatmap.photo is not None
        app.resource_overview.set_collapsed(True)
        app.update()
        assert not app.resource_overview.gauges[0].canvas.winfo_ismapped()
        app.resource_heatmap.set_expanded(False)
        assert len(app.charts)==4 and len(app.replay_charts)==4
        assert not errors,errors
        result['checks'].append('bundled psutil, system graphs, four compact gauges, heatmap and saved appearance')
        result['success']=True
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        if app is not None:
            app.close()
        session.cleanup()
        report_path=Path(report_path)
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['success'] else 1
