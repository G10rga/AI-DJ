"""Import, align and explicitly review a local reference recording."""
import argparse
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.references import ReferenceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    importing = commands.add_parser('import')
    importing.add_argument('manifest', type=Path)
    for name in ('show', 'align', 'refine', 'template', 'review', 'report'):
        command = commands.add_parser(name)
        command.add_argument('reference_id')
        if name == 'review':
            command.add_argument('annotation', type=Path)
        if name == 'refine':
            command.add_argument('--detailed', action='store_true', help='Try 8s windows over wider tempo ratios; require four supporting windows')
        if name in ('align', 'refine', 'template', 'show', 'report'):
            command.add_argument('--output', type=Path)
    args = parser.parse_args()
    store = ReferenceStore(Settings.from_env())
    if args.command == 'import':
        result = store.import_manifest(args.manifest)
    elif args.command == 'show':
        result = store.get(args.reference_id)
    elif args.command == 'align':
        result = store.align(args.reference_id, lambda i, n, title: print(f'[{i+1}/{n}] {title}', flush=True))
    elif args.command == 'refine':
        result = store.refine(args.reference_id, lambda i, n, title: print(f'[{i+1}/{n}] {title}', flush=True), detailed=args.detailed)
    elif args.command == 'template':
        result = store.review_template(args.reference_id)
    elif args.command == 'report':
        result = store.report(args.reference_id)
    else:
        result = store.annotate(args.reference_id, json.loads(args.annotation.read_text(encoding='utf-8-sig')))
    payload = result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    if getattr(args, 'output', None):
        args.output.write_text(payload, encoding='utf-8')
        print(args.output)
    else:
        print(payload)


if __name__ == '__main__':
    main()
