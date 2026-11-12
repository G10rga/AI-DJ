"""Explicit backend validation of the experimental planner on registered source IDs."""
import argparse
import json
from uuid import uuid4

from backend.app.config import Settings
from backend.app.workflow import Workflow
from backend.app.improved_transitions import records_for_sources, generate, compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('track_ids', nargs='+')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--seconds', type=float, default=72.)
    args = parser.parse_args()
    workflow = Workflow(Settings.from_env())
    catalog = {source['id']: source for source in workflow.catalog(internal=True)}
    if len(args.track_ids) < 2 or any(identity not in catalog for identity in args.track_ids):
        raise ValueError('Choose at least two registered catalog IDs in the desired order')
    sources = [catalog[identity] for identity in args.track_ids]
    records = records_for_sources(sources, workflow.settings)
    operation = compare if args.compare else generate
    result = operation(records, [source['path'] for source in sources], workflow.settings, workflow.storage, seconds=args.seconds)
    report = workflow.storage.path('analysis', 'improved-validation-'+uuid4().hex+'.json')
    report.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'report': str(report), 'status': result['status'], 'output': result.get('output'),
        'alternatives': [item['output'] for item in result.get('alternatives', [])],
        'review_items': [{k:item.get(k) for k in ('code','message','join_index','source_index')}
                         for item in result.get('review_items', [])]}, indent=2), flush=True)


if __name__ == '__main__':
    main()
