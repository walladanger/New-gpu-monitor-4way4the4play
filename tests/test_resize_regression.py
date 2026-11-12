"""Use the actual Windows child under an edge, rather than a pure hit-test helper."""
import ctypes
from ctypes import wintypes
import os
import time
import unittest

from dashboard import Dashboard


@unittest.skipUnless(os.name=="nt", "Windows edge target regression")
class ResizeRegressionTests(unittest.TestCase):
    def test_all_visible_edges_have_a_real_resize_target(self):
        app = Dashboard(collect=False)
        try:
            # Keep every growing edge on screen throughout the pointer checks.
            app.geometry('900x650+120+120')
            app.lift()
            app.attributes("-topmost",True)
            deadline = time.monotonic()+.25
            while time.monotonic()<deadline:
                app.update()
                time.sleep(.01)
            app.redraw()
            app.update_idletasks()
            user = ctypes.WinDLL("user32")
            user.WindowFromPoint.argtypes = [wintypes.POINT]
            user.WindowFromPoint.restype = wintypes.HWND
            user.SendMessageW.argtypes = [wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t]
            user.SendMessageW.restype = ctypes.c_ssize_t
            failures = []
            def widgets(parent):
                yield parent
                for child in parent.winfo_children():
                    yield from widgets(child)
            for name,edge,expected in (("left","w",10),("right","e",11),("top","n",12),("bottom","s",15),
                                       ("top-left","nw",13),("top-right","ne",14),("bottom-left","sw",16),("bottom-right","se",17)):
                x,y,w,h=app.winfo_rootx(),app.winfo_rooty(),app.winfo_width(),app.winfo_height()
                px,py={"w":(x+2,y+h//2),"e":(x+w-3,y+h//2),"n":(x+w//2,y+2),"s":(x+w//2,y+h-3),
                       "nw":(x+2,y+2),"ne":(x+w-3,y+2),"sw":(x+2,y+h-3),"se":(x+w-3,y+h-3)}[edge]
                hwnd = user.WindowFromPoint(wintypes.POINT(px,py))
                packed = (px&0xffff)|((py&0xffff)<<16)
                actual = user.SendMessageW(hwnd,0x84,0,packed)
                target=next((widget for widget in widgets(app) if widget.winfo_id()==hwnd),None)
                if target is not None and getattr(target,'_resize_edge',None)==edge:
                    dx=-40 if 'w' in edge else 40 if 'e' in edge else 0
                    dy=-30 if 'n' in edge else 30 if 's' in edge else 0
                    target.event_generate('<ButtonPress-1>',x=2,y=2,rootx=px,rooty=py)
                    target.event_generate('<B1-Motion>',x=2+dx//2,y=2+dy//2,rootx=px+dx//2,rooty=py+dy//2)
                    app.update()
                    self.assertIs(app.grab_current(),target,'resizing must retain the pointer across layout updates')
                    target.event_generate('<B1-Motion>',x=2+dx,y=2+dy,rootx=px+dx,rooty=py+dy)
                    target.event_generate('<ButtonRelease-1>',x=2+dx,y=2+dy,rootx=px+dx,rooty=py+dy)
                    app.update()
                    if dx:
                        self.assertEqual(app.winfo_width(),w+40,name)
                    if dy:
                        self.assertEqual(app.winfo_height(),h+30,name)
                    # Native input may deliver a quick press/release without
                    # any intermediate motion. Its final position still counts.
                    before_w,before_h=app.winfo_width(),app.winfo_height()
                    target.event_generate('<ButtonPress-1>',x=2,y=2,rootx=px,rooty=py)
                    target.event_generate('<ButtonRelease-1>',x=2+dx,y=2+dy,rootx=px+dx,rooty=py+dy)
                    app.update()
                    self.assertEqual(app.winfo_width(),before_w+abs(dx),name+' quick release')
                    self.assertEqual(app.winfo_height(),before_h+abs(dy),name+' quick release')
                elif actual != expected:
                    failures.append(f"{name}: actual pointer target is not a resize grip and hit={actual}")
            self.assertFalse(failures,"; ".join(failures))
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
