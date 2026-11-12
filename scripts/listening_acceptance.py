"""Freeze and inspect milestone-4 jobs in the ordinary main application.

This command never writes listening votes or promotes the experimental pipeline.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
from uuid import uuid4

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.pair_comparisons import enqueue_pair
from backend.app.workflow import Workflow
from scripts.setup_timeline import sha256


PAIRS = [
    ('dub-rhythm', '8c469657d212739b307d7eb9', '6680d8b65d25ed711c3ec594'),
    ('sung-vocals', 'd1bed40a59874c72830d8169', '9bdd31dde9a6ae321bc7b869'),
    ('percussive-vocals', '7a8e0031bdbbef3f95dbc106', '4173ecc4f1e3fb18b93bb2c6'),
    ('hook-to-extended', '1745cfd6a8a28345dc318fdd', '88ed4e11f8b33af698d9c012'),
    ('short-vocal-edits', '6e419ff5ea9c01eaef31b489', '05d1c70d6fc6889d1828e26e'),
]
SET_ORDER = [PAIRS[0][1], PAIRS[0][2], PAIRS[2][1], PAIRS[1][1], PAIRS[3][2]]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def freeze(store):
    catalog = {r['id']: r for r in store.catalog(internal=True)}
    pairs = [{'case': case, 'sources': [catalog[a], catalog[b]]} for case, a, b in PAIRS]
    sources = [s for pair in pairs for s in pair['sources']]
    if len({s['content_hash'] for s in sources}) != 10:
        raise ValueError('The five pairs must have ten distinct originals')
    for s in sources:
        if sha256(Path(s['path'])) != s['content_hash']:
            raise ValueError('Registered original changed: '+s['name'])
    with store.db.connection() as c:
        earlier = [json.loads(r[0]) for r in c.execute('SELECT payload_json FROM workflow_jobs')]
    used = {s['content_hash'] for p in earlier if p.get('pipeline') == 'improved-transitions-1'
            for s in p.get('sources', [])}
    if used.intersection(s['content_hash'] for s in sources):
        raise ValueError('A frozen source was already used by the improved pipeline; do not silently replace it')
    root = store.storage.root/'validation'/('listening-acceptance-'+uuid4().hex)
    root.mkdir(parents=True)
    reference = store.storage.root/'experiments/open-dj/auditions/vocal-handoff-fdc44c762ab34ca8990521d1b53addc0'
    retained = root/'regression'; retained.mkdir()
    files = []
    for name in ('handoff.mp3', 'report.json'):
        original = reference/name
        destination = retained/name
        shutil.copyfile(original, destination)
        if sha256(original) != sha256(destination):
            raise ValueError('Regression copy hash mismatch')
        files.append({'original': str(original), 'retained': str(destination), 'sha256': sha256(destination)})
    modules = ['backend/app/improved_transitions.py', 'backend/app/planning/vocal_preserving.py',
               'backend/app/vocal_rendering.py', 'backend/app/audio/vocal_automation.py',
               'scripts/transition_timing_worker.py', 'scripts/listening_acceptance.py']
    manifest = {'schema': 'listening-acceptance-1', 'created_at': datetime.now(timezone.utc).isoformat(),
        'pairs': pairs, 'set_sources': [catalog[i] for i in SET_ORDER], 'seconds': 72.,
        'selection': 'Pre-result hypotheses from registered versions: dub rhythm, sung vocals, percussive vocals, hook to extended, short vocal edits. Verify actual coverage before acceptance.',
        'independence': 'Ten distinct sources within the five-pair batch; no previous improved-pipeline jobs. Not a claim of training/reference-source independence or owner unfamiliarity.',
        'regression': {'files': files, 'owner_verdict': 'its better', 'full_acceptance': None},
        'implementation_sha256': {name: sha256(PROJECT_ROOT/name) for name in modules},
        'owner_acceptance': None, 'default_approval': None}
    write(root/'manifest.json', manifest)  # Frozen before any job is enqueued.
    jobs = {'manifest_sha256': sha256(root/'manifest.json'), 'pairs': []}
    write(root/'jobs.json', jobs)
    for pair in pairs:
        job = enqueue_pair(store, [s['id'] for s in pair['sources']], pipeline='improved-transitions-1')
        jobs['pairs'].append({'case': pair['case'], 'id': job['id']})
        write(root/'jobs.json', jobs)
    job = store.enqueue_test(None, SET_ORDER, seconds=72., baseline=True, pipeline='improved-transitions-1')
    jobs['set_id'] = job['id']; write(root/'jobs.json', jobs)
    return root


def inspect(store, root):
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    jobs = json.loads((root/'jobs.json').read_text(encoding='utf-8'))
    if sha256(root/'manifest.json') != jobs['manifest_sha256']:
        raise ValueError('Frozen listening definition changed')
    for retained in manifest['regression']['files']:
        if sha256(Path(retained['retained'])) != retained['sha256']:
            raise ValueError('Retained regression artifact changed')
    states = []
    for item in [*jobs['pairs'], {'case': 'continuous-five-song-set', 'id': jobs['set_id']}]:
        job = store.job(item['id'])
        result = job.get('result') or {}
        row = {**item, 'status': job['status'], 'stage': job['stage'], 'error': job.get('error'),
               'song_names': job['payload']['song_names'],
               'review_url': 'http://127.0.0.1:8005/transition-review/'+job['id'],
               'review_items': result.get('review_items', []), 'listening_accepted': None}
        with store.db.connection() as c:
            context = c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?', (job['id'],)).fetchone()
        snapshot = json.loads(context[0]) if context else None
        if snapshot:
            from backend.app.audio.analysis_evidence import foundation_evidence
            from backend.app.planning.vocal_preserving import source_tempos
            row['evidence_summary'] = []
            for record in snapshot['records']:
                evidence = foundation_evidence(record)
                bins = evidence['vocal_activity']
                try:
                    tempos, _ = source_tempos([record])
                except ValueError:
                    tempos = []
                row['evidence_summary'].append({
                    'source_sha256': evidence['reference']['source_sha256'],
                    'duration_seconds': record['effective']['duration_seconds'],
                    'supported_bpm': tempos[0] if tempos else None,
                    'eight_bar_spans': len(evidence['regular_spans']),
                    'observed_vocal_bins': len(bins),
                    'active_vocal_fraction': sum(b['active'] for b in bins)/len(bins) if bins else None,
                    'longest_quieter_passage_seconds': max((p['end']-p['start'] for p in evidence['quieter_passages']), default=0.),
                })
        if job['status'] == 'succeeded' and item['case'] != 'continuous-five-song-set':
            from backend.app.transition_review import media, listening_state
            review = listening_state(store, job['id'])
            row['owner_feedback'] = review
            alternatives = result.get('alternatives', [])
            row['alternatives'] = alternatives
            recipes = {a.get('recipe') for a in alternatives}
            levels = [a['loudness']['integrated_lufs'] for a in alternatives]
            row['level_difference_lu'] = abs(levels[0]-levels[1]) if len(levels) == 2 else None
            row['baseline_comparison_available'] = (recipes == {'plain_crossfade', 'protected_vocal'}
                and row['level_difference_lu'] is not None and row['level_difference_lu'] <= .3)
            row['applied_source_cues'] = [a['plan']['joins'][0]['candidate']['source_cues'] for a in alternatives]
            row['same_source_cues'] = len(alternatives) == 2 and row['applied_source_cues'][0] == row['applied_source_cues'][1]
            for slot in ('a', 'b'):
                media(store, job['id'], slot)  # Verify immutable registered audio.
        elif job['status'] == 'succeeded':
            from backend.app.transition_review import media
            from backend.app.planning.vocal_preserving import validate_plan
            media(store, job['id'])
            validate_plan(result['plan'], snapshot['records'])
            # The saved immutable plan and timing report, rather than a new
            # proposal run, define the actual four handoffs under evaluation.
            row['plan'] = result['plan']
            row['timing'] = result['timing']
            row['audio_url'] = result.get('audio_url')
            row['technical_set_checks'] = {
                'five_ordered_sources': len(result['plan']['sources']) == 5,
                'four_joins': len(result['plan']['joins']) == 4,
                'independent_timing': result['timing']['status'] == 'validated',
                'source_hashes_match_frozen_order': [s['reference']['source_sha256'] for s in result['plan']['sources']] == [s['content_hash'] for s in manifest['set_sources']],
            }
        states.append(row)
    report = {'manifest_sha256': jobs['manifest_sha256'], 'jobs': states,
              'reporting_implementation_sha256': sha256(Path(__file__)),
              'owner_acceptance': None, 'default_approval': None}
    write(root/'status.json', report)
    lines = ['# Milestone 4 listening batch', '',
             'Frozen before results. Case descriptions are hypotheses, not listening findings.',
             'No acceptance or default approval is recorded automatically.', '',
             '| Case | Status | Review |', '|---|---|---|']
    for row in states:
        title = ' → '.join(row['song_names']).replace('|', '\\|')
        lines.append(f'| {row["case"]}: {title} | {row["status"]} | [Open review]({row["review_url"]}) |')
    lines += ['', 'Use [Compare](http://127.0.0.1:8005/compare) for completed A/B jobs and actual votes.',
              'For each pair assess vocal completion, gradual entrance, beat/bar stability and energy; note exact audible defects.',
              'The five-song set additionally checks uninterrupted middle-track progression and all four handoffs.',
              'Needs review is an abstention, not a passed listening test. Mark source boundaries only after listening.',
              'Pair versions may use different evidence-supported cues: assess the complete proposal, not an isolated gain curve.',
              '', 'Regression reference: [retained At Night → Stupidisco](regression/handoff.mp3).',
              'Exact sources, implementation and artifact hashes: manifest.json, jobs.json and status.json.']
    (root/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'root': str(root), 'jobs': [{k:r.get(k) for k in ('case','id','status','stage','error','baseline_comparison_available')} for r in states]}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--session', type=Path)
    parser.add_argument('--watch', action='store_true', help='Refresh the read-only job report until every original batch job reaches a terminal state')
    args = parser.parse_args()
    if args.freeze == bool(args.session):
        parser.error('Choose --freeze or --session PATH')
    store = Workflow(Settings.from_env())
    root = freeze(store) if args.freeze else args.session.resolve(strict=True)
    while True:
        report = inspect(store, root)
        if not args.watch or all(r['status'] not in ('queued', 'running') for r in report['jobs']):
            break
        time.sleep(30)


if __name__ == '__main__':
    main()
