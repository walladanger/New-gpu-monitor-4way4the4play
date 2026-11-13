import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class DiagnosticsTests(unittest.TestCase):
    def run_session(self,folder,extra='',log_dir=None):
        env=os.environ.copy()
        env['GPU_LIVE_GRAPHS_DATA_DIR']=str(folder)
        env.pop('GPU_LIVE_GRAPHS_LOG_DIR',None)
        if log_dir:
            env['GPU_LIVE_GRAPHS_LOG_DIR']=str(log_dir)
        script='import diagnostics,logging,json,sys; diagnostics.configure_logging(); assert "tkinter" not in sys.modules; '+(extra+'; ' if extra else '')+'print(json.dumps({k:str(v) for k,v in diagnostics.session_info().items()}))'
        result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout.strip())

    def test_early_bootstrap_and_unique_complete_session_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            first=self.run_session(folder)
            second=self.run_session(folder)
            self.assertNotEqual(first['path'],second['path'])
            contents=Path(first['path']).read_text(encoding='utf-8')
            self.assertIn('phase=pre_import',contents)
            self.assertIn('phase=shutdown',contents)
            self.assertTrue(list(Path(folder).rglob('*-native.log')))

    def test_selected_folder_copies_current_session_and_next_boot_uses_it(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'selected'
            first=self.run_session(folder,f'diagnostics.set_log_folder({str(destination)!r}); logging.getLogger("gpu_live_graphs").info("last event")')
            copied=destination/Path(first['path']).name
            text=copied.read_text(encoding='utf-8')
            self.assertIn('phase=pre_import',text)
            self.assertIn('last event',text)
            self.assertIn('phase=shutdown',text)
            second=self.run_session(folder)
            # Windows runners may supply TEMP using its 8.3 alias; compare identity.
            self.assertTrue(Path(second['folder']).samefile(destination))
            self.assertNotEqual(Path(second['path']).name,copied.name)

    def test_unavailable_folder_falls_back_and_records_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked=Path(folder)/'file';blocked.write_text('keep')
            result=self.run_session(folder,log_dir=blocked/'logs')
            self.assertEqual(Path(result['folder']),Path(folder)/'logs')
            self.assertIn('fallback',Path(result['path']).read_text(encoding='utf-8'))
            self.assertEqual(blocked.read_text(),'keep')

    def test_relative_destination_is_rejected_without_changing_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            # Catch inside child so rejection doesn't suppress its JSON output.
            script='import diagnostics; diagnostics.configure_logging()\ntry:\n diagnostics.set_log_folder("D:debugging Logs")\nexcept ValueError:\n print("rejected")\nelse:\n raise AssertionError("accepted relative path")'
            env=os.environ.copy();env['GPU_LIVE_GRAPHS_DATA_DIR']=folder;env.pop('GPU_LIVE_GRAPHS_LOG_DIR',None)
            result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('rejected',result.stdout)
            self.assertFalse((Path(folder)/'diagnostic-settings.json').exists())
