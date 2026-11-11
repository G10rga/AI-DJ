"""Start AI-DJ with the project environment: python run.py."""

import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        python = Path(sys.executable)

    env = os.environ.copy()
    if os.name == "nt":
        # Match scripts/local.ps1 on the owner's PC, preserving explicit overrides.
        data = Path("D:/AI-DJ-data")
        if data.is_dir():
            env.setdefault("AI_DJ_DATA_ROOT", str(data))
            data = Path(env["AI_DJ_DATA_ROOT"])
            env.setdefault("NUMBA_CACHE_DIR", str(data / "cache" / "numba"))
            env.setdefault("JOBLIB_TEMP_FOLDER", str(data / "tmp"))
        binaries = Path("D:/Tools/ffmpeg-9.0.2-essentials_build/bin")
        for key, name in (("AI_DJ_FFMPEG", "ffmpeg.exe"), ("AI_DJ_FFPROBE", "ffprobe.exe")):
            if (binaries / name).is_file():
                env.setdefault(key, str(binaries / name))

    try:
        return subprocess.call([str(python), "-m", "scripts.serve"], cwd=root, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
