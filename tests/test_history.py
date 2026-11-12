import csv
from contextlib import closing
import json
from pathlib import Path
import queue
import sqlite3
import tempfile
import time
import unittest

from gpu_data import Reading,Snapshot
from history_store import HistoryStore,restore


def snapshot(wall=None):
    return Snapshot(12345,time.time() if wall is None else wall,(Reading('0','GPU-A','NVIDIA GeForce RTX 3090',0,None,24,41.125,100.25,310),))


class HistoryTests(unittest.TestCase):
    def test_restart_preserves_precision_zero_missing_and_rebases_clock(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'history.sqlite3'
            first=HistoryStore(path)
            self.assertTrue(first.ready.wait(3))
            original=snapshot(time.time()-30)
            first.append(original)
            self.assertTrue(first.flush())
            first.close()
            second=HistoryStore(path)
            self.assertTrue(second.ready.wait(3))
            kind,records=second.messages.get(timeout=2)
            second.close()
            self.assertEqual(kind,'loaded')
            self.assertEqual(len(records),1)
            self.assertEqual(records[0].readings,original.readings)
            self.assertEqual(records[0].wall_time,original.wall_time)
            self.assertAlmostEqual(time.monotonic()-records[0].stamp,30,delta=2)
            self.assertNotEqual(records[0].stamp,12345)

    def test_retention_and_complete_gpu_specific_csv_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'history.sqlite3'
            store=HistoryStore(path,retention=60)
            self.assertTrue(store.ready.wait(3))
            store.messages.get(timeout=1)
            store.append(snapshot(time.time()-120))
            store.append(snapshot(time.time()-10))
            self.assertTrue(store.flush())
            output=Path(temporary)/'saved.csv'
            store.export(output,'GPU-A','RTX 3090')
            kind,value=store.messages.get(timeout=3)
            self.assertEqual(kind,'exported')
            with output.open(encoding='utf-8-sig',newline='') as file:
                rows=list(csv.DictReader(file))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['load_percent'],'0')
            self.assertEqual(rows[0]['vram_used_gib'],'')
            self.assertFalse(output.with_suffix('.csv.partial').exists())
            store.close()
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM samples').fetchone()[0],1)

    def test_corrupt_database_is_preserved_and_writer_closes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'history.sqlite3'
            original=b'not a sqlite database'
            path.write_bytes(original)
            store=HistoryStore(path)
            self.assertTrue(store.ready.wait(3))
            self.assertIn('History unavailable',store.error)
            with self.assertRaises(RuntimeError):
                store.export(Path(temporary)/'x.csv','GPU-A','A')
            store.close()
            self.assertFalse(store.thread.is_alive())
            self.assertEqual(path.read_bytes(),original)

    def test_page_limit_and_bounded_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'history.sqlite3'
            store=HistoryStore(path,max_bytes=256*1024)
            self.assertTrue(store.ready.wait(3))
            for i in range(400):
                value=snapshot(time.time()-400+i)
                while not store.append(value):
                    time.sleep(.01)
            self.assertTrue(store.flush(10))
            store.close()
            self.assertLessEqual(path.stat().st_size,256*1024)
            self.assertFalse(store.thread.is_alive())

    def test_invalid_sensor_payload_is_rejected(self):
        value=snapshot().readings[0].__dict__.copy()
        value['power']='invalid'
        with self.assertRaises(ValueError):
            restore(time.time(),json.dumps([value]),(time.monotonic(),time.time()))


class HistoryDashboardTests(unittest.TestCase):
    def test_restart_restores_graphs_without_claiming_live_readings(self):
        from dashboard import Dashboard
        with tempfile.TemporaryDirectory() as temporary:
            first=Dashboard(collect=False,persist=True,data_dir=temporary)
            first.store.ready.wait(3)
            first.poll_history()
            first.accept(snapshot(time.time()-20))
            first.close()
            second=Dashboard(collect=False,persist=True,data_dir=temporary)
            try:
                self.assertTrue(second.store.ready.wait(3))
                second.poll_history()
                self.assertEqual(second.restored_count,1)
                self.assertEqual(len(second.history),1)
                self.assertEqual(second.available,set())
                self.assertIsNone(second.latest_at)
                second.window_choice.set('1 hour')
                second.update();second.layout_graphs();second.update();second.redraw()
                self.assertTrue(second.charts[0].scene.points)
            finally:
                second.close()
