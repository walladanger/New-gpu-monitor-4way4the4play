"""Saved launch profiles and bounded, provenance-aware app observations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import uuid

import psutil


ADAPTERS = ("Generic EXE", "Ollama", "InvokeAI")
RETENTION = 24 * 60 * 60


@dataclass
class AppProfile:
    id: str
    name: str
    executable: str
    arguments: list[str]
    directory: str
    gpu_uuid: str
    adapter: str = "Generic EXE"

    def validate(self):
        if not self.id or not self.name.strip() or not self.executable.strip():
            raise ValueError("Name and executable are required.")
        if self.adapter not in ADAPTERS or not self.gpu_uuid.startswith("GPU-"):
            raise ValueError("Choose a supported app type and a physical NVIDIA GPU.")
        if not isinstance(self.arguments, list) or not all(isinstance(a, str) for a in self.arguments):
            raise ValueError("Arguments must be a list of text values.")

    def launch_error(self, available_uuids):
        if not Path(self.executable).is_file():
            return "Executable missing. Use Browse to repair its path."
        if not Path(self.directory).is_dir():
            return "Working directory missing. Choose an existing folder."
        if self.gpu_uuid not in available_uuids:
            return "Selected GPU is unavailable. Choose another physical GPU."
        return None


class ProfileStore:
    VERSION = 1

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != self.VERSION:
            raise ValueError("Profiles use an unsupported schema version.")
        profiles = [AppProfile(**item) for item in data["profiles"]]
        for profile in profiles:
            profile.validate()
        return profiles

    def save(self, profiles):
        for profile in profiles:
            profile.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": self.VERSION, "profiles": [asdict(p) for p in profiles]}, indent=2)
        handle, temporary = tempfile.mkstemp(prefix="app-profiles-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def new_profile(name, executable, arguments, directory, gpu_uuid, adapter="Generic EXE"):
    return AppProfile(uuid.uuid4().hex, name, str(Path(executable).resolve()), list(arguments),
                      str(Path(directory).resolve()), gpu_uuid, adapter)


def external_process(profile):
    """Only identify known server names; a generic matching EXE is ambiguous."""
    names = {"Ollama": {"ollama.exe", "ollama app.exe"},
             "InvokeAI": {"invokeai.exe", "invokeai-launcher.exe"}}.get(profile.adapter, set())
    if not names:
        return None
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if (process.info["name"] or "").lower() in names:
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


class LaunchManager:
    def __init__(self):
        self.managed = {}

    def state(self, profile):
        identity = self.managed.get(profile.id)
        if identity:
            pid, created, child = identity
            if child.poll() is not None:
                self.managed.pop(profile.id, None)
                return "Exited", None
            try:
                process = psutil.Process(pid)
                if abs(process.create_time() - created) < 0.01 and process.is_running():
                    if process.status() != psutil.STATUS_ZOMBIE:
                        return "Launched here", process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self.managed.pop(profile.id, None)
            return "Exited", None
        external = external_process(profile)
        if external:
            return "Already running elsewhere", external
        return "Not running", None

    def launch(self, profile, available_uuids):
        error = profile.launch_error(available_uuids)
        if error:
            raise ValueError(error)
        state, process = self.state(profile)
        if state in ("Launched here", "Already running elsewhere"):
            return state, process
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = profile.gpu_uuid
        child = subprocess.Popen([profile.executable, *profile.arguments], cwd=profile.directory,
                                 env=environment, shell=False,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process = psutil.Process(child.pid)
        self.managed[profile.id] = (child.pid, process.create_time(), child)
        return "Launched here", process


class ActivityStore:
    """One observation per profile per minute; absent minutes remain unknown."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS observations (profile TEXT, minute INTEGER, "
                       "state TEXT, pid INTEGER, created REAL, gpu TEXT, device_util REAL, "
                       "source TEXT, PRIMARY KEY(profile, minute))")
            db.execute("CREATE INDEX IF NOT EXISTS observation_time ON observations(minute)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, profile, state, process, reading, now=None):
        now = time.time() if now is None else now
        minute = int(now // 60)
        try:
            pid, created = (process.pid, process.create_time()) if process else (None, None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pid, created = None, None
        # This utilization belongs to the device, never to the process.
        utilization = reading.utilization if reading else None
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?)",
                       (profile.id, minute, state, pid, created, profile.gpu_uuid,
                        utilization, "NVIDIA device-wide" if reading else "Unavailable"))
            db.execute("DELETE FROM observations WHERE minute < ?", (int((now - RETENTION) // 60),))

    def timeline(self, profile_id, now=None):
        now = time.time() if now is None else now
        start = int((now - RETENTION) // 60)
        with self._connect() as db:
            return db.execute("SELECT minute,state,pid,created,device_util,source FROM observations "
                              "WHERE profile=? AND minute>=? ORDER BY minute", (profile_id, start)).fetchall()
