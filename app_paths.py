"""Writable per-user storage shared by source and installed builds."""
import os
from pathlib import Path


def data_directory():
    override=os.environ.get('GPU_LIVE_GRAPHS_DATA_DIR')
    root=Path(override) if override else Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'GPU Live Graphs'
    root.mkdir(parents=True,exist_ok=True)
    return root


def user_path(name):
    path=data_directory()/name
    path.mkdir(parents=True,exist_ok=True)
    return path
