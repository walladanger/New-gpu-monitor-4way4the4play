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
        app=Dashboard(collect=False,persist=True,preferences=True,data_dir=session.name)
        assert app.store.ready.wait(5)
        app.poll_history()
        app.report_callback_exception=lambda *args:errors.append(str(args[1]))
        now=time.monotonic()
        for i in range(30):
            app.accept(Snapshot(now-29+i,time.time()-29+i,(Reading('0','GPU-SELF-TEST','NVIDIA GeForce RTX 3090',float(i),2.5,24,42.5,100.25,310),)))
        app.paused=True;app.frozen_at=now
        for _ in range(5):
            app.update();time.sleep(.05)
        app.redraw();app.update()
        assert len(app.charts)==4 and all(c.scene for c in app.charts)
        result['checks'].append('four charts rendered')
        assert app.chrome.native
        original=app.chrome.bounds()
        app.chrome.toggle_maximize();app.update()
        app.chrome.toggle_maximize();app.update()
        assert app.chrome.bounds()[2:]==original[2:]
        result['checks'].append('frameless maximize/restore')
        app.charts[0].pins.add(app.history[-5],'GPU-SELF-TEST')
        detached=app.open_window(app.charts[0]);app.update();app.redraw()
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
        app.charts[0].series_colors['GPU-SELF-TEST']='#123456'
        app.window_choice.set('1 hour')
        app.close()
        app=Dashboard(collect=False,persist=True,preferences=True,data_dir=session.name)
        assert app.store.ready.wait(5)
        app.poll_history()
        assert len(app.history)==30
        assert app.available==set() and app.latest_at is None
        assert app.charts[0].series_colors['GPU-SELF-TEST']=='#123456'
        assert app.window_choice.get()=='1 hour'
        result['checks'].append('SQLite history and preferences survive restart')
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
