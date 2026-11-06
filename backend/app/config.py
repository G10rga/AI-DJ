"""Local settings. Environment variables override defaults; no implicit .env loading."""
from dataclasses import dataclass
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_root: Path = PROJECT_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    max_upload_bytes: int = 512 * 1024 * 1024
    min_free_bytes: int = 2 * 1024**3
    heavy_workers: int = 1
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    def __post_init__(self):
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Local mode requires a loopback host")
        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid port")
        if self.max_upload_bytes <= 0 or self.min_free_bytes < 0:
            raise ValueError("Invalid storage limits")
        if self.heavy_workers != 1:
            raise ValueError("Only one heavy worker is supported")
        object.__setattr__(self, "data_root", Path(self.data_root).resolve())

    @classmethod
    def from_env(cls):
        return cls(
            data_root=Path(os.environ.get("AI_DJ_DATA_ROOT", str(PROJECT_ROOT / "data"))),
            host=os.environ.get("AI_DJ_HOST", "127.0.0.1"),
            port=int(os.environ.get("AI_DJ_PORT", "8000")),
            max_upload_bytes=int(os.environ.get("AI_DJ_MAX_UPLOAD_BYTES", str(512 * 1024**2))),
            min_free_bytes=int(os.environ.get("AI_DJ_MIN_FREE_BYTES", str(2 * 1024**3))),
            ffmpeg=os.environ.get("AI_DJ_FFMPEG", "ffmpeg"),
            ffprobe=os.environ.get("AI_DJ_FFPROBE", "ffprobe"),
        )
