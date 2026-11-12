"""Bounded SQLite archive owned exclusively by one background worker.

Uses sqlite3 transactions and parameter binding documented at
https://docs.python.org/3.11/library/sqlite3.html . Monotonic clocks are never
persisted: wall timestamps are rebased onto this process when restoring.
"""
from dataclasses import asdict
import json
import logging
import math
from pathlib import Path
import queue
import sqlite3
import threading
import time
import uuid

from gpu_data import Reading, Snapshot
from exporting import export_csv

RETENTION_SECONDS=24*60*60
MAX_BYTES=128*1024*1024
MAX_RESTORE=4000


def serialize(snapshot):
    return json.dumps([asdict(r) for r in snapshot.readings],allow_nan=False,separators=(',',':'))


def restore(wall,payload,anchor):
    if len(payload)>256000:
        raise ValueError('Stored sample is too large')
    monotonic_now,wall_now=anchor
    values=json.loads(payload)
    if not isinstance(values,list) or len(values)>128:
        raise ValueError('Invalid stored readings')
    readings=tuple(Reading(**r) for r in values)
    for reading in readings:
        if not all(isinstance(getattr(reading,k),str) for k in ('index','uuid','name')):
            raise ValueError('Invalid stored GPU identity')
        for key in ('utilization','memory','capacity','temperature','power','power_limit'):
            value=getattr(reading,key)
            if value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):
                raise ValueError('Invalid stored sensor value')
    return Snapshot(monotonic_now+(wall-wall_now),wall,readings)


class HistoryStore:
    def __init__(self,path,retention=RETENTION_SECONDS,max_bytes=MAX_BYTES):
        self.path=Path(path)
        self.retention=retention
        self.max_bytes=max_bytes
        self.session=uuid.uuid4().hex
        self.tasks=queue.Queue(maxsize=256)
        self.messages=queue.Queue()
        self.error=None
        self.closed=False
        self.ready=threading.Event()
        self.thread=threading.Thread(target=self._run,name='GPU history',daemon=True)
        self.thread.start()

    def append(self,snapshot,error=None):
        if self.closed:
            return False
        try:
            self.tasks.put_nowait(('append',snapshot,error))
            return True
        except queue.Full:
            self.error='History write queue is full; monitoring continues in memory.'
            return False

    def export(self,path,uid,name):
        if self.closed or (self.ready.is_set() and self.error and self.error.startswith('History unavailable')):
            raise RuntimeError(self.error or 'History writer is closed.')
        try:
            self.tasks.put_nowait(('export',Path(path),uid,name))
        except queue.Full as error:
            raise RuntimeError('History writer is busy. Try again shortly.') from error

    def flush(self,timeout=5):
        done=threading.Event()
        self.tasks.put(('flush',done),timeout=timeout)
        return done.wait(timeout)

    def close(self,timeout=5):
        if self.closed:
            return
        self.closed=True
        try:
            self.tasks.put(('close',),timeout=timeout)
        except queue.Full:
            self.error='History writer did not drain before shutdown.'
            return
        self.thread.join(timeout)
        if self.thread.is_alive():
            self.error='History shutdown timed out; some pending records may not be saved.'

    def _open(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.path,timeout=.5)
        try:
            # Single worker/connection: rollback journal keeps disk limits simple.
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('PRAGMA synchronous=FULL')
            version=connection.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):
                raise ValueError('History database is from a newer application version')
            if version==0:
                connection.execute('PRAGMA auto_vacuum=INCREMENTAL')
                connection.execute('CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,session TEXT NOT NULL,wall REAL NOT NULL,payload TEXT NOT NULL,error TEXT)')
                connection.execute('CREATE INDEX IF NOT EXISTS samples_wall ON samples(wall)')
                connection.execute('PRAGMA user_version=1')
                connection.commit()
            page_size=connection.execute('PRAGMA page_size').fetchone()[0]
            self.page_budget=max(64,self.max_bytes//page_size)
            connection.execute(f'PRAGMA max_page_count={self.page_budget}')
            return connection
        except Exception:
            connection.close()
            raise

    def _trim(self,connection):
        cutoff=time.time()-self.retention
        with connection:
            connection.execute('DELETE FROM samples WHERE wall<?',(cutoff,))
            connection.execute('DELETE FROM samples WHERE id IN (SELECT id FROM samples ORDER BY wall DESC,id DESC LIMIT -1 OFFSET 100000)')
        pages=connection.execute('PRAGMA page_count').fetchone()[0]
        free=connection.execute('PRAGMA freelist_count').fetchone()[0]
        if pages-free>self.page_budget*.9:
            # Evict oldest records before reaching SQLite's hard page limit.
            with connection:
                connection.execute('DELETE FROM samples WHERE id IN (SELECT id FROM samples ORDER BY wall,id LIMIT 1000)')
        connection.execute('PRAGMA incremental_vacuum(64)')

    def _load(self,connection):
        anchor=(time.monotonic(),time.time())
        rows=connection.execute('SELECT wall,payload FROM samples WHERE wall>=? AND wall<=? ORDER BY wall DESC,id DESC LIMIT ?',
                                (anchor[1]-3600,anchor[1]+1,MAX_RESTORE)).fetchall()
        records=[]
        for wall,payload in reversed(rows):
            try:
                records.append(restore(wall,payload,anchor))
            except (ValueError,TypeError,KeyError,RecursionError,OverflowError):
                logging.getLogger('gpu_live_graphs').warning('Skipped an invalid archived sample')
        self.messages.put(('loaded',records))

    def _export(self,connection,path,uid,name):
        anchor=(time.monotonic(),time.time())
        cursor=connection.execute('SELECT wall,payload FROM samples WHERE wall>=? AND wall<=? ORDER BY wall,id',
                                  (anchor[1]-self.retention,anchor[1]+1))
        def records():
            for wall,payload in cursor:
                snapshot=restore(wall,payload,anchor)
                if snapshot.gpu(uid):
                    yield snapshot
        # Write into a temporary sibling and expose only the completed export.
        temporary=path.with_suffix(path.suffix+'.partial')
        try:
            iterator=iter(records())
            first=next(iterator,None)
            if first is None:
                raise ValueError('No saved readings for this GPU in the retained history.')
            import itertools
            export_csv(temporary,itertools.chain((first,),iterator),uid,name)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.messages.put(('exported',str(path)))

    def _run(self):
        connection=None
        try:
            connection=self._open()
            self._trim(connection)
            self._load(connection)
        except (OSError,sqlite3.Error,ValueError) as error:
            if connection is not None:
                connection.close()
                connection=None
            self.error=f'History unavailable: {error}. Monitoring continues in memory.'
            self.messages.put(('error',self.error))
            logging.getLogger('gpu_live_graphs').error(self.error)
        finally:
            self.ready.set()
        try:
            count=0
            while True:
                task=self.tasks.get()
                try:
                    if task[0]=='close':
                        if connection is not None:
                            self._trim(connection)
                        break
                    if task[0]=='flush':
                        task[1].set()
                    elif connection is not None:
                        if task[0]=='append':
                            snapshot,error=task[1:]
                            payload=serialize(snapshot)
                            if len(payload)>256000:
                                raise ValueError('Snapshot exceeds the archive record limit')
                            if count%30==0:
                                self._trim(connection)
                            with connection:
                                connection.execute('INSERT INTO samples(session,wall,payload,error) VALUES(?,?,?,?)',
                                                   (self.session,snapshot.wall_time,payload,error))
                            count+=1
                            if self.error:
                                self.error=None
                                self.messages.put(('recovered',None))
                        elif task[0]=='export':
                            self._export(connection,*task[1:])
                except (OSError,sqlite3.Error,ValueError,TypeError) as error:
                    self.error=f'History storage: {error}'
                    self.messages.put(('error',self.error))
                    logging.getLogger('gpu_live_graphs').error(self.error)
                finally:
                    self.tasks.task_done()
                if task[0]=='close':
                    break
        finally:
            if connection is not None:
                connection.close()
