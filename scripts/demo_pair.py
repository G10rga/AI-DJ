"""Generate synthetic audio on the data disk and render a reproducible smoke demo."""
from backend.app.config import Settings
from backend.app.storage import Storage
from backend.app.audio.analyze import analyze
from backend.app.audio.pair import render_pair
from scripts.synthetic_audio import write_fixture


def main():
    settings = Settings.from_env()
    storage = Storage(settings.data_root)
    storage.initialize()
    # Fixtures stay in the data area, never in the source tree.
    a = storage.path("uploads", "synthetic-120.wav")
    b = storage.path("uploads", "synthetic-124.wav")
    write_fixture(a)
    write_fixture(b, bpm=124, tone=330)
    results = []
    for path in (a, b):
        print(f"Analyzing {path.name}...", flush=True)
        results.append(analyze(path, settings, storage))
    report = render_pair((a, b), tuple(results), settings, storage, starts=(0.5, 0.5),
                         seconds=22, bpms=(120, 124), style="smooth")
    print(f"Audio: {report['output']}\nReport: {report['report']}")
    print(f"Duration: {report['audio']['duration']:.3f}s; overlap: {report['overlap_seconds']:.3f}s")


if __name__ == "__main__":
    main()
