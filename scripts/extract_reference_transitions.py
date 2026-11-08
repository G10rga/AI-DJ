"""Generate immutable transition drafts for listening review, never automatic labels."""
import argparse
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.reference_review import ReferenceReviewStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = ReferenceReviewStore(Settings.from_env()).extract(args.reference_id,
        lambda i, n, title: print(f'[{i+1}/{n}] {title}', flush=True))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps({'draft_id': result['id'], 'counts': result['counts'],
                      'bounded_drafts': sum(t['draft']['mix_start'] is not None for t in result['transitions'])}, indent=2))


if __name__ == '__main__':
    main()
