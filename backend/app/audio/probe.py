"""Audio subprocess boundary: explicit arguments, timeouts, and useful failures."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import subprocess
from backend.app.config import Settings


class AudioError(RuntimeError):
    pass


def run_audio(args: list[str], timeout: float = 600) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioError(f"Unable to run {Path(args[0]).name}: {exc}") from exc
    if result.returncode:
        raise AudioError(f"{Path(args[0]).name} failed: {result.stderr[-3000:].strip()}")
    return result.stdout


@dataclass(frozen=True)
class AudioInfo:
    duration: float
    sample_rate: int
    channels: int
    codec: str


def probe(path: Path, settings: Settings) -> AudioInfo:
    path = Path(path).resolve(strict=True)
    payload = run_audio([settings.ffprobe, "-v", "error", "-select_streams", "a:0",
                         "-show_entries", "stream=codec_name,sample_rate,channels,duration:format=duration",
                         "-of", "json", str(path)], timeout=30)
    try:
        data = json.loads(payload)
        stream = data["streams"][0]
        duration = stream.get("duration")
        if duration in {None, "N/A"}:
            duration = data["format"]["duration"]
        info = AudioInfo(float(duration), int(stream["sample_rate"]), int(stream["channels"]), stream["codec_name"])
        if not math.isfinite(info.duration) or info.duration <= 0 or min(info.channels, info.sample_rate) <= 0:
            raise ValueError("Invalid audio metadata")
        return info
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AudioError("No usable audio stream with a known duration") from exc
