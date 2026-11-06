"""Application-owned paths; client filenames never determine storage locations."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4


class Storage:
    AREAS = {"uploads", "analysis", "tmp", "renders", "plans", "models"}

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def path(self, area: str, name: str) -> Path:
        if area not in self.AREAS:
            raise ValueError("Unknown storage area")
        if not name or name in {".", ".."} or any(c in name for c in '/\\:'):
            raise ValueError("Expected a single storage filename")
        result = (self.root / area / name).resolve()
        if not result.is_relative_to(self.root / area):
            raise ValueError("Path escapes storage area")
        return result

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for area in self.AREAS:
            directory = self.root / area
            directory.mkdir(exist_ok=True)
            if directory.resolve() != directory:
                raise ValueError("Storage areas must not be redirected")

    def new_upload_path(self) -> Path:
        return self.path("uploads", uuid4().hex)

    def require_space(self, required_bytes: int, reserve_bytes: int):
        if required_bytes < 0 or reserve_bytes < 0:
            raise ValueError("Space requirements must be nonnegative")
        if shutil.disk_usage(self.root).free < required_bytes + reserve_bytes:
            raise OSError("Insufficient free disk space for this operation")

    @contextmanager
    def temporary_directory(self):
        with tempfile.TemporaryDirectory(dir=self.root / "tmp", prefix="job-") as name:
            yield Path(name)
