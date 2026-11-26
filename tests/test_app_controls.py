"""Launch and activity checks that do not require NVIDIA hardware."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

from app_controls import ActivityStore, LaunchManager, ProfileStore, new_profile
from gpu_data import Reading
from gpu_data import Snapshot


class AppControlsTests(unittest.TestCase):
    def test_apps_tab_saves_selection_and_disables_missing_gpu(self):
        from dashboard import Dashboard
        with tempfile.TemporaryDirectory() as root:
            app = Dashboard(collect=False, persist=True, data_dir=root)
            try:
                reading = Reading("1", "GPU-stable", "Test card", 42, None, None, None, None, None)
                app.accept(Snapshot(time.monotonic(), time.time(), (reading,)), save=False)
                app.show_apps()
                tab = app.apps_page
                tab.add()
                tab._put(tab.name, "Worker")
                tab._put(tab.executable, sys.executable)
                tab._put(tab.directory, root)
                tab.gpu.set(next(iter(tab.gpu_values)))
                tab.save()
                self.assertEqual(ProfileStore(Path(root) / "app-profiles.json").load()[0].gpu_uuid, "GPU-stable")
                app.available.clear()
                tab.refresh()
                self.assertEqual(str(tab.launch_button.cget("state")), "disabled")
            finally:
                app.close()

    def test_profiles_follow_uuid_and_missing_paths_disable_launch(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "profiles.json"
            profile = new_profile("Worker", sys.executable, ["-V"], root, "GPU-stable")
            ProfileStore(path).save([profile])
            loaded = ProfileStore(path).load()[0]
            self.assertEqual(loaded.gpu_uuid, "GPU-stable")
            self.assertIsNone(loaded.launch_error({"GPU-stable"}))
            self.assertIn("GPU", loaded.launch_error({"GPU-other"}))
            loaded.executable = str(Path(root) / "missing.exe")
            self.assertIn("Executable", loaded.launch_error({"GPU-stable"}))

    def test_child_receives_selected_uuid_without_changing_parent(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "environment.txt"
            code = "import os,pathlib;pathlib.Path(r'%s').write_text(os.environ['CUDA_VISIBLE_DEVICES'])" % output
            profile = new_profile("Child", sys.executable, ["-c", code], root, "GPU-selected")
            manager = LaunchManager()
            state, process = manager.launch(profile, {"GPU-selected"})
            self.assertEqual(state, "Launched here")
            process.wait(timeout=10)
            self.assertEqual(output.read_text(), "GPU-selected")
            self.assertEqual(manager.state(profile)[0], "Exited")

    def test_activity_stores_device_provenance_and_leaves_gaps(self):
        with tempfile.TemporaryDirectory() as root:
            store = ActivityStore(Path(root) / "activity.sqlite3")
            profile = new_profile("Worker", sys.executable, [], root, "GPU-selected")
            reading = Reading("1", "GPU-selected", "Test", 42, None, None, None, None, None)
            now = time.time()
            store.record(profile, "Launched here", None, reading, now - 180)
            store.record(profile, "Exited", None, None, now)
            rows = store.timeline(profile.id, now)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][4:], (42, "NVIDIA device-wide"))
            self.assertEqual(rows[1][4:], (None, "Unavailable"))
            self.assertGreater(rows[1][0] - rows[0][0], 1)


if __name__ == "__main__":
    unittest.main()
