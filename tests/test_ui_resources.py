import gc
import threading
import tkinter as tk
import unittest
import weakref

from PIL import Image
from ui_resources import PhotoImage,StringVar,drain_resources


class UIResourceTests(unittest.TestCase):
    def test_worker_gc_defers_image_and_variable_cleanup_to_ui_thread(self):
        root=tk.Tk();root.withdraw()
        automatic=gc.isenabled()
        gc.disable()
        try:
            photo=PhotoImage(Image.new('RGB',(10,10)),master=root)
            variable=StringVar(root,'alive')
            image_name,variable_name=str(photo),str(variable)
            reference=weakref.ref(photo)
            cycle=[photo,variable];cycle.append(cycle)
            del cycle,photo,variable
            worker=threading.Thread(target=gc.collect,daemon=True)
            worker.start();worker.join(3)
            self.assertFalse(worker.is_alive(),'GC must never wait for Tcl from a worker')
            self.assertIsNone(reference())
            self.assertEqual(root.tk.call('image','type',image_name),'photo')
            self.assertEqual(root.getvar(variable_name),'alive')
            self.assertGreaterEqual(drain_resources(),2)
            with self.assertRaises(tk.TclError):
                root.tk.call('image','type',image_name)
            self.assertFalse(root.tk.getboolean(root.tk.call('info','exists',variable_name)))
        finally:
            root.destroy();drain_resources()
            if automatic:
                gc.enable()
