"""Run real registered-pair foundation validation without changing mixer defaults."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings
from backend.app.timeline_analysis import analyze_registered_pair
from backend.app.workflow import Workflow
from backend.app.timelines import canonical


def old_records(workflow):
    with workflow.db.connection() as connection:
        return {name: [dict(row) for row in connection.execute('SELECT * FROM '+name)]
                for name in ('timelines', 'timeline_corrections')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('track_ids', nargs=2)
    args = parser.parse_args()
    workflow = Workflow(Settings.from_env())
    before = old_records(workflow)
    result = analyze_registered_pair(workflow, args.track_ids)
    again = analyze_registered_pair(workflow, args.track_ids)
    if canonical(result) != canonical(again):
        raise ValueError('Repeated analysis did not return identical pinned evidence')
    after = old_records(workflow)
    for table, rows in before.items():
        now = {canonical(row) for row in after[table]}
        if any(canonical(row) not in now for row in rows):
            raise ValueError('Existing prediction/correction was modified')
    summary = []
    for source in result['sources']:
        evidence = source['evidence']
        timeline = source['timeline']['effective']
        if not timeline['embeddings'] or not evidence['vocal_activity'] or not evidence['vocal_chunks']:
            raise ValueError('Real model evidence is missing')
        summary.append({'catalog_id': source['catalog_id'], 'reference': evidence['reference'],
            'duration_seconds': timeline['duration_seconds'],
            'beats': len(evidence['beats']['times']), 'downbeats': len(evidence['downbeats']['times']),
            'regular_eight_bar_spans': len(evidence['regular_spans']),
            'mert_windows': len(timeline['embeddings']), 'vocal_bins': len(evidence['vocal_activity']),
            'vocal_chunks': len(evidence['vocal_chunks']), 'quieter_candidates': len(evidence['quieter_passages']),
            'structural_candidates': len(evidence['structural_changes']),
            'coverage_end': evidence['vocal_activity'][-1]['end']})
    directory = workflow.storage.root/'analysis'/('foundation-validation-'+uuid4().hex)
    directory.mkdir()
    payload = directory/'evidence.json'
    payload.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    report = {'version': result['version'], 'sources': summary, 'cache_reuse_identical': True,
        'prior_predictions_unchanged': len(before['timelines']),
        'prior_corrections_unchanged': len(before['timeline_corrections']),
        'evidence_sha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
        'listening_accepted': None, 'default_changed': False}
    (directory/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'report': str(directory/'report.json'), 'sources': summary}, indent=2), flush=True)


if __name__ == '__main__':
    main()
