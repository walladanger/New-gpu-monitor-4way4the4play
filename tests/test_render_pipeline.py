import threading
import time
import unittest

from render_pipeline import RenderPipeline


class PipelineTests(unittest.TestCase):
    def test_latest_settings_replace_stale_jobs_and_apply_on_owner_thread(self):
        pipeline=RenderPipeline()
        owner=object();started=threading.Event();release=threading.Event()
        drawn=[];applied=[];main_thread=threading.get_ident()
        def draw(value):
            self.assertNotEqual(threading.get_ident(),main_thread)
            drawn.append(value)
            if value==0:
                started.set();self.assertTrue(release.wait(5))
            return value
        def apply(value):
            self.assertEqual(threading.get_ident(),main_thread)
            applied.append(value)
        try:
            pipeline.request(owner,0,'old',draw,(0,),{},apply)
            self.assertTrue(started.wait(5))
            for value in range(1,101):
                pipeline.request(owner,value,'new',draw,(value,),{},apply)
            self.assertEqual(len(pipeline.states),1)
            release.set()
            deadline=time.monotonic()+5
            while pipeline.busy():
                pipeline.poll();time.sleep(.005)
                self.assertLess(time.monotonic(),deadline)
            self.assertEqual(drawn,[0,100])
            self.assertEqual(applied,[100])
        finally:
            release.set();pipeline.close()

    def test_live_updates_do_not_starve_completed_frames(self):
        pipeline=RenderPipeline();applied=[]
        try:
            owner=object()
            pipeline.request(owner,1,'same settings',lambda:1,(),{},applied.append)
            time.sleep(.02)
            pipeline.request(owner,2,'same settings',lambda:2,(),{},applied.append)
            pipeline.poll()
            self.assertEqual(applied,[1])
            deadline=time.monotonic()+5
            while pipeline.busy():
                pipeline.poll();time.sleep(.005)
                self.assertLess(time.monotonic(),deadline)
            self.assertEqual(applied,[1,2])
        finally:
            pipeline.close()

    def test_discarded_window_never_gets_a_late_presentation(self):
        pipeline=RenderPipeline();applied=[]
        try:
            owner=object()
            pipeline.request(owner,1,None,lambda:1,(),{},applied.append)
            pipeline.discard(owner)
            pipeline.poll()
            self.assertFalse(applied)
        finally:
            pipeline.close()
