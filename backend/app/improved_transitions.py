"""Shared opt-in backend for improved Generate and Compare (public UI follows in M3)."""
from pathlib import Path

from .audio.mdx import sha256_file
from .planning.vocal_preserving import PIPELINE, plan_set, review
from .timeline_analysis import analyze_timeline, FOUNDATION_PROFILE
from .timelines import TimelineStore
from .vocal_rendering import render_plan, check_live


def records_for_sources(sources, settings, *, pinned=None, live=lambda: True):
    store = TimelineStore(settings.data_root)
    if pinned is not None and len(pinned) != len(sources):
        raise ValueError('One pinned evidence record per source is required')
    records = []
    for i, source in enumerate(sources):
        check_live(live)
        if sha256_file(source['path']) != source['content_hash']:
            raise ValueError('Selected registered source changed')
        if pinned is not None:
            record = pinned[i]
        else:
            keys = analyze_timeline(source['path'], settings, with_vocals=True, profile=FOUNDATION_PROFILE,
                                    expected_content_hash=source['content_hash'])
            record = store.get(**keys)
        if record['effective']['content_hash'] != source['content_hash']:
            raise ValueError('Pinned evidence belongs to a different original')
        records.append(record)
    return records


def generate(records, paths, settings, storage, *, seconds=72., predictions=None,
             selected_ids=None, live=lambda: True, renderer=render_plan, corrections=None):
    check_live(live)
    result = plan_set(records, seconds=seconds, predictions=predictions, selected_ids=selected_ids, corrections=corrections)
    if result['status'] != 'planned':
        return {**result, 'pipeline': PIPELINE}
    rendered = renderer(result['plan'], records, paths, settings, storage, live=live)
    return {**rendered, 'pipeline': PIPELINE, 'proposals': result['proposals']}


def compare(records, paths, settings, storage, *, seconds=72., predictions=None,
            rejected_ids=(), live=lambda: True, renderer=render_plan, corrections=None):
    if len(records) != 2:
        raise ValueError('Compare requires exactly two ordered sources')
    storage.initialize()
    check_live(live)
    result = plan_set(records, seconds=seconds, predictions=predictions,corrections=corrections)
    if result['status'] != 'planned':
        return {**result, 'pipeline': PIPELINE}
    candidates = [candidate for candidate in result['proposals'][0]['candidates'] if candidate['id'] not in set(rejected_ids)]
    # Prefer different recipes when both are safe; never fabricate an unsafe
    # alternative just to fill A/B, nor replace a failed selected candidate.
    chosen = candidates[:1]
    other = next((c for c in candidates[1:] if c['recipe'] != chosen[0]['recipe']), None) if chosen else None
    if other is None and len(candidates) > 1:
        other = candidates[1]
    if other:
        chosen.append(other)
    if len(chosen) != 2:
        return {'status': 'needs_review', 'pipeline': PIPELINE, 'review_items': [review('comparison_alternative_missing',
            'Two distinct safe alternatives are unavailable; no rejected candidate was restored.')], 'proposals': result['proposals']}
    # Withhold both alternatives until the complete pair passes validation.
    from .storage import Storage
    import json
    from uuid import uuid4
    with storage.temporary_directory() as work:
        staging = Storage(work/'comparison'); staging.initialize()
        reports = []
        for candidate in chosen:
            report = generate(records, paths, settings, staging, seconds=seconds, predictions=predictions,
                              selected_ids=[candidate['id']], live=live, renderer=renderer,corrections=corrections)
            if report['status'] != 'validated':
                return {**report, 'alternatives': []}
            reports.append(report)
        if abs(reports[0]['loudness']['integrated_lufs']-reports[1]['loudness']['integrated_lufs']) > .3:
            return {'status': 'needs_review', 'pipeline': PIPELINE, 'alternatives': [],
                'review_items': [review('comparison_level_mismatch', 'Safe alternatives could not meet the same listening level.') ]}
        check_live(live)
        alternatives = []
        for report in reports:
            output = storage.path('renders', 'improved-comparison-'+uuid4().hex+'.mp3')
            Path(report['output']).replace(output)
            report['output'] = str(output)
            output.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
            alternatives.append(report)
    return {'status': 'validated', 'pipeline': PIPELINE, 'alternatives': alternatives,
            'review_items': [], 'preference_learning_eligible': False, 'listening_accepted': None}


def execute_job(store, job, owner, progress):
    """Both existing job entry points dispatch here only for a pinned opt-in payload.

    M3 will expose the option and durable review/resume/media operations. Until
    then the structured backend result is validated or needs_review, never a
    questionable legacy fallback or an automatically activated mix.
    """
    payload = job['payload']
    if payload.get('preference_model'):
        return {'status': 'needs_review', 'pipeline': PIPELINE, 'review_items': [review('preference_features_unavailable',
            'This pipeline requires versioned features for its new controls before learned preference ranking can be applied.')]}
    live = lambda: store.live(job['id'], owner)
    progress('Preparing pinned vocal-preserving evidence', .05)
    sources = payload['sources']
    records = records_for_sources(sources, store.settings, pinned=payload.get('foundation_records'), live=live)
    from .transition_review import capture
    capture(store,job,owner,records)
    corrections={key:{**value,'review_job_id':payload.get('parent_job_id',job['id']),
        'review_revision':payload.get('review_revision',0)} for key,value in payload.get('corrections',{}).items()}
    paths = [Path(source['path']) for source in sources]
    predictions = payload.get('improved_predictions')
    if not payload.get('baseline', True) and predictions is None:
        return {'status': 'needs_review', 'pipeline': PIPELINE, 'review_items': [review('model_proposal_missing',
            'The optional cue model has no compatible pinned proposal; baseline settings were not substituted.')]}
    progress('Planning continuous vocal-preserving transitions and validating actual audio', .4)
    if job['kind'] == 'pair_audition':
        return compare(records, paths, store.settings, store.storage, seconds=payload.get('seconds', 72),
            predictions=predictions, rejected_ids=payload.get('rejected_candidate_ids', ()), live=live,corrections=corrections)
    return generate(records, paths, store.settings, store.storage, seconds=payload.get('seconds', 72),
                    predictions=predictions, selected_ids=payload.get('selected_candidate_ids'), live=live,corrections=corrections)
