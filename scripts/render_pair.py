"""Analyze two local files and render a reviewable transition prototype."""
import argparse
import json
from pathlib import Path
import sys
from backend.app.audio.analyze import analyze
from backend.app.audio.pair import render_pair
from backend.app.audio.probe import AudioError
from backend.app.config import Settings
from backend.app.storage import Storage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--a-in", type=float, help="First excerpt source start in seconds")
    parser.add_argument("--b-in", type=float, help="Second excerpt source start in seconds")
    parser.add_argument("--a-bpm", type=float, help="Verified BPM override")
    parser.add_argument("--b-bpm", type=float, help="Verified BPM override")
    parser.add_argument("--seconds", type=float, default=120, help="Target output seconds per excerpt")
    parser.add_argument("--bars", type=int, choices=(8, 32), default=8)
    parser.add_argument("--style", choices=("auto", "smooth", "boundary_fade"), default="auto")
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        storage = Storage(settings.data_root)
        storage.initialize()
        paths = (args.first.resolve(strict=True), args.second.resolve(strict=True))
        results = []
        for path in paths:
            print(f"Analyzing {path.name}...", flush=True)
            result = analyze(path, settings, storage)
            print(f"  BPM: {result['bpm']}; beat confidence: {result['beat_confidence']}", flush=True)
            results.append(result)
        if args.analyze_only:
            print(json.dumps(results, indent=2))
            return 0
        print("Rendering transition...", flush=True)
        report = render_pair(paths, tuple(results), settings, storage, starts=(args.a_in, args.b_in),
                             seconds=args.seconds, bars=args.bars, bpms=(args.a_bpm, args.b_bpm), style=args.style)
        print(f"Audio: {report['output']}\nReport: {report['report']}")
        print(f"Style: {report['style']}; overlap: {report['overlap_seconds']:.2f}s")
        for warning in report["warnings"]:
            print(f"Review: {warning}")
        return 0
    except (OSError, ValueError, AudioError) as exc:
        print(f"Cannot render pair: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
