"""Run from the repository root: python -m scripts.doctor."""
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.storage import Storage


def run_tool(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace")
        if result.returncode:
            return None
        return result.stdout + result.stderr
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    settings = Settings.from_env()
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Platform: {platform.platform()}; logical CPUs: {os.cpu_count()}")
    print(f"SQLite: {sqlite3.sqlite_version}; heavy workers: {settings.heavy_workers}")
    storage = Storage(settings.data_root)
    storage.initialize()
    Database(storage.root / "app.sqlite3").initialize()
    storage.require_space(0, settings.min_free_bytes)
    print(f"Storage: {storage.root}; free: {shutil.disk_usage(storage.root).free / 1024**3:.1f} GiB")
    failed = False
    for label, executable in (("FFmpeg", settings.ffmpeg), ("ffprobe", settings.ffprobe)):
        output = run_tool([executable, "-version"])
        print(f"{label}: {output.splitlines()[0] if output else 'MISSING or unusable'}")
        failed |= output is None
    filters = run_tool([settings.ffmpeg, "-hide_banner", "-filters"])
    rubberband = bool(filters and any(" rubberband " in line for line in filters.splitlines()))
    print(f"FFmpeg Rubber Band filter: {'available' if rubberband else 'MISSING (pitch-preserving stretch not verified)'}")
    failed |= not rubberband
    if failed:
        print("Install an FFmpeg build with ffprobe and librubberband, then rerun this check.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
