"""Keyboard-accessible launch profile editor and 24-hour observation view."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import time
import tkinter as tk
from tkinter import filedialog, ttk
import uuid

from app_controls import ADAPTERS, ActivityStore, AppProfile, LaunchManager, ProfileStore
from graph_scene import BG, PANEL, TEXT, MUTED
from gpu_data import gpu_labels


class AppsTab(tk.Frame):
    def __init__(self, parent, dashboard):
        super().__init__(parent, bg=BG)
        self.dashboard = dashboard
        self.profile_store = ProfileStore(dashboard.data_dir / "app-profiles.json") if dashboard.data_dir else None
        self.activity = None
        if dashboard.data_dir:
            try:
                self.activity = ActivityStore(dashboard.data_dir / "app-activity.sqlite3")
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.activity_error = str(exc)
            else:
                self.activity_error = None
        else:
            self.activity_error = "Activity storage is unavailable in this test session."
        self.launcher = LaunchManager()
        self.profiles = []
        self.selected_id = None
        self.last_recorded = None
        self.gpu_values = {}
        if self.profile_store:
            try:
                self.profiles = self.profile_store.load()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.load_error = str(exc)
            else:
                self.load_error = None
        else:
            self.load_error = "Profiles are unavailable in this test session."
        self._build()
        self._list_profiles()

    def _build(self):
        tk.Label(self, text="Apps · GPU for next launch", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=24, pady=(18, 4))
        tk.Label(self, text="Select a physical NVIDIA GPU by UUID. This applies when the app starts; GPU assignment for a generic EXE is unverified.",
                 bg=BG, fg=MUTED, wraplength=900, justify="left").pack(anchor="w", padx=24)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=12)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 18))
        tk.Label(left, text="Saved profiles", bg=BG, fg=TEXT).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=26, height=16, bg=PANEL, fg=TEXT,
                                  selectbackground="#355778", exportselection=False)
        self.listbox.pack(fill="y", expand=True, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self._select)
        tk.Button(left, text="Add app", command=self.add, bg=PANEL, fg=TEXT).pack(fill="x", pady=3)
        tk.Button(left, text="Remove profile", command=self.remove, bg=PANEL, fg=TEXT).pack(fill="x", pady=3)
        form = tk.Frame(body, bg=BG)
        form.pack(side="left", fill="both", expand=True)
        self.name = self._entry(form, "Name")
        self.executable = self._entry(form, "Executable (.exe)")
        tk.Button(form, text="Browse…", command=self.browse, bg=PANEL, fg=TEXT).pack(anchor="w", pady=(0, 5))
        self.directory = self._entry(form, "Working directory")
        self.arguments = self._entry(form, "Arguments (optional)")
        tk.Label(form, text="App type", bg=BG, fg=TEXT).pack(anchor="w")
        self.adapter = ttk.Combobox(form, values=ADAPTERS, state="readonly")
        self.adapter.set(ADAPTERS[0])
        self.adapter.pack(fill="x", pady=(2, 7))
        tk.Label(form, text="Physical GPU · UUID → in-process cuda:0", bg=BG, fg=TEXT).pack(anchor="w")
        self.gpu = ttk.Combobox(form, state="readonly")
        self.gpu.pack(fill="x", pady=(2, 8))
        actions = tk.Frame(form, bg=BG)
        actions.pack(anchor="w")
        self.save_button = tk.Button(actions, text="Save profile", command=self.save, bg=PANEL, fg=TEXT)
        self.save_button.pack(side="left", padx=(0, 8))
        self.launch_button = tk.Button(actions, text="Launch", command=self.launch, bg=PANEL, fg=TEXT)
        self.launch_button.pack(side="left")
        self.status = tk.Label(form, bg=BG, fg=TEXT, justify="left", anchor="w", wraplength=650)
        self.status.pack(fill="x", pady=(12, 6))
        self.timeline = tk.Label(form, bg=BG, fg=MUTED, justify="left", anchor="w", wraplength=650)
        self.timeline.pack(fill="x")
        self.timeline_canvas = tk.Canvas(form, height=32, bg=PANEL, highlightthickness=0)
        self.timeline_canvas.pack(fill="x", pady=(6, 2))
        self.timeline_canvas.bind("<Configure>", lambda _event: self._draw_timeline())
        tk.Label(form, text="24 hours ago                                           Now · blue = observed, gray = unknown",
                 bg=BG, fg=MUTED, justify="left").pack(anchor="w")
        self.refresh()

    def _entry(self, parent, label):
        tk.Label(parent, text=label, bg=BG, fg=TEXT).pack(anchor="w")
        entry = tk.Entry(parent, bg=PANEL, fg=TEXT, insertbackground=TEXT)
        entry.pack(fill="x", pady=(2, 7))
        return entry

    def _put(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _list_profiles(self):
        self.listbox.delete(0, "end")
        for profile in self.profiles:
            self.listbox.insert("end", profile.name)
        if self.profiles:
            index = next((i for i, p in enumerate(self.profiles) if p.id == self.selected_id), 0)
            self.listbox.selection_set(index)
            self._select()
        else:
            self.selected_id = None
            self.status.configure(text=self.load_error or "No profiles yet. Add an app to choose its GPU for next launch.")
            self.launch_button.configure(state="disabled")
            self._draw_timeline()

    def _profile(self):
        return next((p for p in self.profiles if p.id == self.selected_id), None)

    def _select(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        profile = self.profiles[selection[0]]
        self.selected_id = profile.id
        self._put(self.name, profile.name)
        self._put(self.executable, profile.executable)
        self._put(self.directory, profile.directory)
        self._put(self.arguments, subprocess_arguments(profile.arguments))
        self.adapter.set(profile.adapter)
        self.refresh()

    def add(self):
        self.listbox.selection_clear(0, "end")
        self.selected_id = None
        for entry in (self.name, self.executable, self.directory, self.arguments):
            self._put(entry, "")
        self.adapter.set(ADAPTERS[0])
        self.gpu.set("")
        self.status.configure(text="Choose an EXE and a physical GPU, then save the profile.")
        self.launch_button.configure(state="disabled")
        self.name.focus_set()

    def browse(self):
        path = filedialog.askopenfilename(parent=self, title="Choose an executable",
                                           filetypes=[("Windows executable", "*.exe")])
        if path:
            self._put(self.executable, path)
            if not self.directory.get():
                self._put(self.directory, str(Path(path).parent))
            if not self.name.get():
                self._put(self.name, Path(path).stem)

    def _args(self):
        text = self.arguments.get().strip()
        if not text:
            return []
        # shlex with Windows mode keeps quoted groups; remove their enclosing quotes.
        return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
                for part in shlex.split(text, posix=False)]

    def save(self):
        if not self.profile_store:
            self.status.configure(text="Profile storage unavailable.")
            return
        try:
            selected = self.gpu_values.get(self.gpu.get())
            profile = AppProfile(self.selected_id or uuid.uuid4().hex,
                                 self.name.get().strip(), str(Path(self.executable.get()).resolve()),
                                 self._args(), str(Path(self.directory.get()).resolve()),
                                 selected or "", self.adapter.get())
            profile.validate()
            revised = list(self.profiles)
            current = self._profile()
            if current:
                revised[revised.index(current)] = profile
            else:
                revised.append(profile)
            self.profile_store.save(revised)
            self.profiles = revised
            self.selected_id = profile.id
            self.load_error = None
            self._list_profiles()
            self.status.configure(text="Profile saved. Selection applies only when this profile launches next.")
        except (OSError, ValueError) as exc:
            self.status.configure(text=f"Save failed: {exc}")

    def remove(self):
        profile = self._profile()
        if profile and self.profile_store:
            self.profiles.remove(profile)
            try:
                self.profile_store.save(self.profiles)
            except OSError as exc:
                self.profiles.append(profile)
                self.status.configure(text=f"Remove failed: {exc}")
                return
            self._list_profiles()

    def launch(self):
        profile = self._profile()
        if not profile:
            return
        try:
            state, _ = self.launcher.launch(profile, self.dashboard.available)
        except (OSError, ValueError) as exc:
            self.status.configure(text=f"Launch failed: {exc}")
            return
        self.refresh()

    def refresh(self):
        devices = self.dashboard.devices
        labels = gpu_labels(devices)
        self.gpu_values = {f"GPU {devices[uid].index} · {labels[uid]} · {uid}": uid for uid in devices}
        self.gpu.configure(values=list(self.gpu_values))
        profile = self._profile()
        if not profile:
            return
        self.gpu.set(next((text for text, uid in self.gpu_values.items() if uid == profile.gpu_uuid), ""))
        error = profile.launch_error(self.dashboard.available)
        state, process = self.launcher.state(profile)
        self.launch_button.configure(state="disabled" if error or state in ("Launched here", "Already running elsewhere") else "normal")
        if error:
            self.status.configure(text=error)
        elif state == "Already running elsewhere":
            self.status.configure(text="Already running elsewhere · selection applies after a managed restart. No process was stopped.")
        else:
            uptime = f" · uptime {int(time.time() - process.create_time())} s" if process else ""
            self.status.configure(text=f"{state}{uptime} · GPU assignment unverified · {profile.gpu_uuid} → CUDA cuda:0")
        if self.activity:
            rows = self.activity.timeline(profile.id)
            if rows:
                last = rows[-1]
                stamp = datetime.fromtimestamp(last[0] * 60).strftime("%b %d %I:%M %p")
                known = len(rows)
                gaps = max(0, 1440 - known)
                utilization = f"{last[4]:g}% device-wide GPU use" if last[4] is not None else "GPU telemetry unavailable"
                self.timeline.configure(text=f"24 h observations: {known} known minutes · {gaps} unknown minutes (including monitor closure).\nLast observed {stamp}: {last[1]}; {utilization}. Per-app use and token/image counts: Unavailable.")
            else:
                self.timeline.configure(text="No 24 h observations yet. Per-app GPU use and token/image counts: Unavailable.")
            self._draw_timeline(rows)
        else:
            self.timeline.configure(text="24 h activity unavailable: " + (self.activity_error or "Storage error"))

    def _draw_timeline(self, rows=None):
        canvas = self.timeline_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        canvas.create_rectangle(0, 5, width, 25, fill="#45505b", outline="")
        profile = self._profile()
        if rows is None and profile and self.activity:
            rows = self.activity.timeline(profile.id)
        end_minute = int(time.time() // 60)
        for minute, *_rest in rows or []:
            x = (minute - (end_minute - 1440)) * width / 1440
            canvas.create_rectangle(x, 5, max(x + 1, x + width / 1440), 25,
                                    fill="#70a9ff", outline="")

    def observe(self, snapshot):
        if not self.activity or not self.profiles:
            return
        minute = int(snapshot.wall_time // 60)
        if minute == self.last_recorded:
            return
        self.last_recorded = minute
        for profile in self.profiles:
            state, process = self.launcher.state(profile)
            self.activity.record(profile, state, process, snapshot.gpu(profile.gpu_uuid), snapshot.wall_time)
        if self.dashboard.active_tab == "apps":
            self.refresh()


def subprocess_arguments(arguments):
    return subprocess.list2cmdline(arguments)
