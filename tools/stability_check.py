"""Exercise our own windows with bounded data; optionally sample live NVIDIA data.

No GPU settings or workload are changed. Reports contain counts, timing, and
application failures rather than screenshots or unrelated process information.
"""
import argparse
from dataclasses import asdict
import gc
import json
import math
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard
from gpu_data import Reading,Snapshot


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=180)
    parser.add_argument('--cycles',type=int,default=100)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    errors=[]
    report={'success':False,'mode':'live NVIDIA' if args.live else 'synthetic','cycles':0,'callback_errors':errors}
    started=time.monotonic()
    with tempfile.TemporaryDirectory() as temporary:
        app=Dashboard(collect=args.live,persist=True,preferences=True,data_dir=temporary)
        app.report_callback_exception=lambda kind,value,tb:errors.append(f'{kind.__name__}: {value}')
        try:
            app.store.ready.wait(5);app.poll_history()
            if not args.live:
                records=[]
                now,wall=time.monotonic(),time.time()
                for index in range(3600):
                    readings=tuple(Reading(str(gpu),f'GPU-STRESS-{gpu}','NVIDIA GeForce RTX 3090' if gpu<2 else 'NVIDIA GeForce RTX 4070',
                        50+45*math.sin(index*.09+gpu),12+gpu,24 if gpu<2 else 12,50+10*math.sin(index*.02),150+100*math.sin(index*.03+gpu),310)
                        for gpu in range(3))
                    records.append(Snapshot(now-3599+index,wall-3599+index,readings))
                app.history.extend(records[:-1]);app.accept(records[-1])
            app.window_choice.set('1 hour')
            app.update();app.layout_graphs();app.update();app.redraw()
            cycle=0
            render_times=[]
            while time.monotonic()-started<args.seconds or cycle<args.cycles:
                if cycle<args.cycles:
                    app.chrome.set_bounds((60,60,500 if cycle%2 else 1400,800 if cycle%2 else 1000))
                    app.update();app.layout_graphs();app.update()
                    if cycle%10==0:
                        app.chrome.toggle_maximize();app.update()
                        app.chrome.toggle_maximize();app.update()
                    if cycle%5==0:
                        window=app.open_window(app.charts[cycle%4]);app.update();app.redraw();window.close()
                    cycle+=1
                if args.live:
                    app.update()
                else:
                    app.poll_history()
                    if cycle%10==0:
                        latest=app.history[-1]
                        app.accept(Snapshot(time.monotonic(),time.time(),latest.readings))
                before=time.monotonic()
                app.redraw();app.update()
                render_times.append(time.monotonic()-before)
                if errors:
                    raise RuntimeError('A callback failed')
                if len(render_times)%30==0:
                    print(json.dumps({'elapsed_s':round(time.monotonic()-started),'cycles':cycle,'devices':len(app.devices),'samples':len(app.history)}),flush=True)
                time.sleep(.2)
            app.save_preferences()
            assert app.store.flush(10)
            report.update(success=not errors and (not args.live or bool(app.devices)),cycles=cycle,
                          elapsed_s=round(time.monotonic()-started,2),devices=len(app.devices),samples_in_memory=len(app.history),
                          max_render_s=round(max(render_times),3),average_render_s=round(sum(render_times)/len(render_times),3),
                          history_error=app.store.error)
            assert len(app.history)<=4000
            assert not app.detached
        except Exception as error:
            report['error']=str(error)
        finally:
            app.close();gc.collect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    return 0 if report['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
