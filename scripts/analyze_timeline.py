"""Build immutable musical timelines through the shared application service."""
import argparse
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.timeline_analysis import analyze_timeline, FOUNDATION_PROFILE, LEGACY_PROFILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--with-vocals', action='store_true')
    parser.add_argument('--foundation', action='store_true', help='Versioned float/relative-vocal evidence profile')
    args = parser.parse_args()
    settings = Settings.from_env()
    for source in args.sources:
        print(json.dumps(analyze_timeline(source, settings, with_vocals=args.with_vocals,
            profile=FOUNDATION_PROFILE if args.foundation else LEGACY_PROFILE), indent=2))


if __name__ == '__main__':
    main()
