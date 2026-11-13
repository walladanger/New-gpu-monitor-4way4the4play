"""Bounded Pillow rendering jobs. Tk presentation always stays on its owning thread."""
from concurrent.futures import ThreadPoolExecutor
import logging
import time


def draw_frame(draw, args, kwargs):
    start = time.perf_counter()
    return draw(*args, **kwargs), time.perf_counter()-start


class RenderPipeline:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='Graph renderer')
        self.states = {}
        self.completed = 0
        self.max_seconds = 0
        self.serial = 0

    def request(self, owner, key, presentation, draw, args, kwargs, apply):
        state = self.states.setdefault(owner, {'future': None, 'done': None, 'done_id':0})
        self.serial+=1
        state['wanted_id']=self.serial
        state['wanted'] = (key, presentation, draw, args, kwargs, apply)
        if state['future'] is None and key != state['done']:
            self.start(state)
        elif state['future'] is None:
            state['done_id']=self.serial

    def start(self, state):
        request = state['wanted']
        state['running'] = request
        state['running_id']=state['wanted_id']
        state['future'] = self.executor.submit(draw_frame, request[2], request[3], request[4])

    def poll(self):
        for state in list(self.states.values()):
            future = state['future']
            if future is None or not future.done():
                continue
            request = state['running']
            state['future'] = None
            state['done'] = request[0]
            state['done_id']=state['running_id']
            try:
                scene, elapsed = future.result()
                self.completed += 1
                self.max_seconds = max(self.max_seconds, elapsed)
                if elapsed > .25:
                    logging.getLogger('gpu_live_graphs').info('Slow graph render %.3fs', elapsed)
                if request[1] == state['wanted'][1]:
                    request[5](scene)
            except Exception:
                logging.getLogger('gpu_live_graphs').exception('Graph render failed')
            if state['wanted'][0] != state['done']:
                self.start(state)
            else:
                state['done_id']=state['wanted_id']

    def busy(self):
        return any(state['future'] is not None for state in self.states.values())

    def discard(self, owner):
        state = self.states.pop(owner, None)
        if state and state['future']:
            state['future'].cancel()

    def close(self):
        self.states.clear()
        self.executor.shutdown(wait=True, cancel_futures=True)
