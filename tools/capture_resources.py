"""Capture only the demo application's new resource views, never the desktop.

Run on Windows normally, or with DISPLAY pointing at an isolated Linux test
display. Sensor values are explicitly synthetic and no collector is started.
"""
import argparse
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard
from system_data import SystemSnapshot
from tools.capture_screenshots import populate,capture


def pump(app):
    deadline=time.monotonic()+.7
    while time.monotonic()<deadline:
        app.update();time.sleep(.01)
    app.redraw();app.wait_for_renders();app.update_idletasks()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs'/'images')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=Dashboard(collect=False,async_render=True)
    errors=[]
    app.report_callback_exception=lambda kind,value,tb:errors.append(str(value))
    def snap(name):
        pump(app)
        app.live.configure(text='DEMO',fg='#ffbd69')
        app.status.configure(text='DOCUMENTATION DEMO · synthetic resource readings · real application UI')
        app.update_idletasks()
        path=args.output/name
        if os.name=='nt':
            capture(app,path)
        else:
            from PIL import ImageGrab
            box=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())
            ImageGrab.grab(bbox=box,xdisplay=os.environ['DISPLAY']).save(path,optimize=True)
        print(path,flush=True)
    try:
        app.geometry('1400x1080+40+40')
        populate(app)
        end,wall=app.frozen_at,app.history[-1].wall_time
        for i in range(300):
            values={'cpu:total':35+20*math.sin(i*.035),'cpu:clock':4.1 if i<100 else 4.4 if i<220 else 4.2,
                    'ram:used':32+i/100,'ram:available':32-i/100,'ram:cached':4,'ram:total':64,
                    'ram:used_pct':(32+i/100)/64*100,'disk:total:read':30+20*math.sin(i*.1),
                    'disk:total:write':8+4*math.sin(i*.08),'disk:volume:C:used':512,'disk:volume:C:free':512,'disk:volume:C:total':1024}
            values.update({f'cpu:thread:{n}':max(0,min(100,45+35*math.sin(i*.04+n*.7))) for n in range(16)})
            app.accept_system(SystemSnapshot(end-299+i,wall-299+i,values))
        pump(app)
        rack_height=float(app.viewport.cget('scrollregion').split()[3])
        app.viewport.yview_moveto(max(0,(app.resource_overview.winfo_y()-10)/rack_height))
        snap('09-system-overview.png')
        app.show_system();pump(app)
        app.system_panels['cpu'].sensor_button.invoke()
        snap('10-system-details.png')
        app.glass_popup.close()
        app.show_live();app.resource_heatmap.set_expanded(True)
        pump(app)
        app.resource_heatmap.set_metric('cpu:clock')
        app.viewport.yview_moveto(1)
        snap('11-resource-heatmap.png')
        if errors:
            raise RuntimeError('; '.join(errors))
    finally:
        app.close()


if __name__=='__main__':
    main()
