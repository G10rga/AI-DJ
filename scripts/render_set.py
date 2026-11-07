"""Render selected audio files or a directory through the shared set pipeline."""
import argparse
import json
from uuid import uuid4
from backend.app.config import Settings
from backend.app.storage import Storage
from backend.app.library import discover, collect_entries, persist_plan
from backend.app.planning.planner import build_plan
from backend.app.rendering import render_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='Audio paths or directories')
    parser.add_argument('--excerpt-seconds', type=float, default=144)
    parser.add_argument('--contextual', action='store_true', help='Use available musical timelines and waveform-validated contextual candidates')
    args = parser.parse_args()
    settings = Settings.from_env()
    storage = Storage(settings.data_root)
    storage.initialize()
    entries = collect_entries(discover(args.inputs), settings, storage)
    plan, details = build_plan(entries, uuid4().hex, requested_seconds=args.excerpt_seconds)
    if args.contextual:
        from backend.app.planning.contextual_set import contextualize_plan
        plan, details = contextualize_plan(entries, plan, details, settings, storage)
    persist_plan(entries, plan, settings)
    state = render_set(entries, plan, details, settings, storage)
    print(json.dumps({'output': state['output'], 'attempt_id': state['attempt_id'],
                      'published': state['published']}, indent=2))


if __name__ == '__main__':
    main()
