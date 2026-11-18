"""Regression coverage for exact sample replay and archived session selection."""
import tempfile
import time
import unittest
from pathlib import Path

from gpu_data import Reading, Snapshot
from history_store import HistoryStore
from replay import ReplayTrack


def snapshot(wall, load, uuid="GPU-A", missing=False):
    return Snapshot(wall - 500.0, wall, (
        Reading("0", uuid, "NVIDIA GeForce RTX 3090",
                load, None if missing else 3.25, 24, 52, 140, 310),
    ))


class ReplayTrackTests(unittest.TestCase):
    def test_replays_only_recorded_readings_at_original_intervals_and_stops(self):
        records = (snapshot(1000, 10), snapshot(1001, 20), snapshot(1005, 90))
        track = ReplayTrack(records, session="run-1")
        self.assertEqual(track.current().readings[0].utilization, 10)
        self.assertFalse(track.playing)
        track.play(20.0)
        track.advance(20.5)
        self.assertEqual(track.current().readings[0].utilization, 10)
        track.advance(21.0)
        self.assertEqual(track.current().readings[0].utilization, 20)
        track.advance(25.0)
        self.assertEqual(track.current().readings[0].utilization, 90)
        self.assertFalse(track.playing)
        self.assertEqual(track.fraction, 1)
        track.seek(0.0)
        self.assertEqual(track.current().wall_time, 1000)

    def test_seek_and_speed_do_not_interpolate_unrecorded_sensor_values(self):
        track = ReplayTrack((snapshot(1000, 0), snapshot(1004, 50, missing=True)))
        track.seek(.5)
        self.assertEqual(track.current().readings[0].utilization, 0)
        self.assertFalse(track.available())  # The held sample is stale at t=1002.
        track.seek(1)
        self.assertIsNone(track.current().readings[0].memory)
        self.assertEqual([r.wall_time for r in track.history(3600)], [1000, 1004])
        track.seek(0)
        track.speed = 2.0
        track.play(10)
        track.advance(12)
        self.assertEqual(track.current().wall_time, 1004)

    def test_future_samples_and_other_sessions_are_never_in_frame(self):
        track = ReplayTrack((snapshot(1000, 0), snapshot(1001, 10),
                             snapshot(1002, 20)), session="latest")
        track.seek(.5)
        history = track.history(3600)
        self.assertEqual([r.wall_time for r in history], [1000, 1001])
        self.assertEqual(set(track.devices), {"GPU-A"})

    def test_empty_and_single_sample_recordings_are_safe(self):
        empty = ReplayTrack(())
        self.assertIsNone(empty.current())
        empty.play(0)
        empty.advance(100)
        self.assertFalse(empty.playing)
        single = ReplayTrack((snapshot(1000, 1),))
        single.play(0)
        self.assertFalse(single.playing)
        self.assertEqual(single.fraction, 1)


class ReplayArchiveTests(unittest.TestCase):
    def test_latest_session_loads_from_sqlite_without_editing_recorded_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "history.sqlite3"
            now = time.time()
            first = HistoryStore(path)
            self.assertTrue(first.ready.wait(5))
            self.assertTrue(first.append(snapshot(now-5, 10)))
            self.assertTrue(first.flush())
            first.close()

            second = HistoryStore(path)
            try:
                self.assertTrue(second.ready.wait(5))
                second.append(snapshot(now-2, 20))
                second.append(snapshot(now-1, 30, missing=True))
                self.assertTrue(second.replay_latest())
                deadline = time.monotonic() + 5
                result = None
                while time.monotonic() < deadline:
                    while not second.messages.empty():
                        kind, data = second.messages.get_nowait()
                        if kind == "replay_loaded":
                            result = data
                            break
                    if result:
                        break
                    time.sleep(.01)
                self.assertIsNotNone(result)
                self.assertEqual(result["session"], second.session)
                self.assertEqual([s.readings[0].utilization for s in result["records"]], [20, 30])
                self.assertIsNone(result["records"][-1].readings[0].memory)
                self.assertEqual(result["records"][-1].wall_time, now-1)
            finally:
                second.close()




class ReplayDashboardTests(unittest.TestCase):
    def test_replay_tab_does_not_override_live_stream_or_future_samples(self):
        from dashboard import Dashboard
        app = Dashboard(collect=False)
        try:
            now = time.time()
            first, second = snapshot(now-4, 10), snapshot(now, 90)
            app.accept(first)
            app.accept(second)
            original_live = tuple(app.history)

            app.show_replay()
            app.update()
            self.assertEqual(app.active_tab, "replay")
            self.assertFalse(app.live_page.winfo_ismapped())
            self.assertTrue(app.replay_page.winfo_ismapped())
            self.assertEqual(len(app.replay_charts), 4)
            self.assertEqual(len(app.replay_track.records), 2)
            self.assertEqual(app.replay_context()[0][-1].wall_time, first.wall_time)
            self.assertEqual(app.replay_context()[-1], frozenset({"GPU-A"}))
            app.replay_end()
            self.assertEqual(app.replay_context()[0][-1].wall_time, second.wall_time)
            app.show_live()
            app.update()
            self.assertEqual(app.active_tab, "live")
            self.assertEqual(tuple(app.history), original_live)
            self.assertTrue(app.live_page.winfo_ismapped())
        finally:
            app.close()

if __name__ == "__main__":
    unittest.main()
