"""Analyze a local library, learn ordering/style groups and save a complete plan."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from backend.app.audio.analyze import analyze
from backend.app.audio.pair import render_pair
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import MixPlan
from backend.app.planning.learning import fit_library, VERSION
from backend.app.planning.planner import build_plan
from backend.app.planning.rhythm import analyze_rhythm
from backend.app.storage import Storage
from backend.app.library import discover, collect_entries, persist_plan

EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aiff', '.aif', '.ogg'}


def write_summary(path, artifact):
    plan = MixPlan.from_json(json.dumps(artifact['plan']))
    details = artifact['planning']
    tracks = {track['entry_id']: track for track in details['tracks']}
    total = sum(excerpt.output_duration for excerpt in plan.excerpts)-sum(join.overlap_seconds for join in plan.transitions)
    lines = ['# ML mix plan', '', f'Method: {details["method"]}. {len(plan.excerpts)} uploaded entries retained.',
             f'Planned duration: {total/60:.1f} minutes. This is a plan, not a rendered full set.', '',
             '| # | Track | Source seconds | Source / target BPM | Next handoff |',
             '| --- | --- | --- | --- | --- |']
    for i, excerpt in enumerate(plan.excerpts):
        name = Path(tracks[excerpt.track_id]['path']).name.replace('|', '\\|')
        join = plan.transitions[i] if i < len(plan.transitions) else None
        label = 'Phrase-aligned cut' if join and join.style == 'phrase_cut' else f'{join.bars} bars / {join.style}' if join and join.bars else 'Review required' if join else 'End'
        lines.append(f'| {i+1} | {name} | {excerpt.source_in:.2f}-{excerpt.source_out:.2f} | '
                     f'{excerpt.source_bpm:.2f} / {excerpt.target_bpm:.2f} | {label} |')
    lines += ['', '## Joins requiring review', '']
    flagged = [i for i, join in enumerate(plan.transitions) if join.style == 'boundary_fade']
    for i in flagged:
        reason = '; '.join(details['joins'][i]['downgrades']) or '; '.join(plan.transitions[i].warnings)
        lines.append(f'- Join {i+1}: {reason}')
    if not flagged:
        lines.append('No boundary handoffs were required by the planning guards. Musical quality still needs listening.')
    if artifact.get('preview_attempts'):
        lines += ['', '## Auditions', '']
        for attempt in artifact['preview_attempts']:
            if attempt['status'] == 'succeeded':
                lines.append(f'- Join {attempt["join"]}: [Listen to preview]({Path(attempt["output"]).as_posix()})')
            else:
                lines.append(f'- Join {attempt["join"]}: validation failed: {attempt["reason"]}')
    lines += ['', '## Limits', '', 'Learned similarity/pair groups are unsupervised, not human-rated quality predictions.',
              'Cue support does not establish lyric or phrase endings. Every render still requires waveform validation.',
              'Model metadata: '+Path(artifact['model_path']).as_posix(), '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def preview_join(entries, plan, details, settings, storage, join):
    index = join-1
    if not 0 <= index < len(plan.transitions):
        raise ValueError('Preview join is outside the planned tracklist')
    transition = plan.transitions[index]
    contextual = details.get('contextual', {}).get('joins', [])
    selected = contextual[index].get('selected') if index < len(contextual) else None
    if selected:
        from backend.app.planning.candidate_store import CandidateStore
        from backend.app.auditions import render_candidate
        candidate = CandidateStore(storage.root).load(selected['candidate_id'])
        sources = {e['entry_id']: e['path'] for e in entries}
        report = render_candidate(candidate, selected['validation'], sources, settings, storage)
        return {'output': report['output'], 'report': str(Path(report['output']).with_suffix('.json')),
                'candidate_id': candidate['id']}
    if transition.style == 'boundary_fade':
        raise ValueError('This join is marked for boundary review; choose a beatmatched join to audition')
    lookup = {entry['entry_id']: entry for entry in entries}
    first, second = plan.excerpts[index:index+2]
    a, b = lookup[first.track_id], lookup[second.track_id]
    # Use the actual planned outgoing/incoming overlap, with a short context
    # on each side. A preview is not a rendered full set.
    beat = 60/first.target_bpm
    overlap = transition.overlap_seconds
    seconds = min(overlap+16*beat, first.output_duration, second.output_duration)
    a_start = first.source_out-seconds*first.target_bpm/first.source_bpm
    if a_start < first.source_in:
        seconds = first.output_duration
        a_start = first.source_in
    if (b['analysis']['audio']['duration']-second.source_in)*second.source_bpm/second.target_bpm < seconds:
        raise ValueError('Incoming excerpt lacks sufficient preview context')
    print(f'Audition join {join}: {Path(a["path"]).name} -> {Path(b["path"]).name}', flush=True)
    report = render_pair((Path(a['path']), Path(b['path'])), (a['analysis'], b['analysis']), settings, storage,
                         starts=(a_start, second.source_in), seconds=seconds, bars=transition.bars,
                         bpms=(first.source_bpm, second.source_bpm), style='eq_swap', target_bpm=first.target_bpm)
    command = [sys.executable, '-m', 'scripts.render_stem_pair', report['report'],
               '--vocal-fade-bars', '8' if transition.bars == 32 else '4',
               '--blend-profile', 'long_groove' if transition.bars == 32 else 'standard']
    with storage.temporary_directory() as temporary:
        pointer = temporary/'audition-result.json'
        subprocess.run(command+['--result-file', str(pointer)], check=True)
        result = json.loads(pointer.read_text(encoding='utf-8'))
    return {**result, 'reference_pair_report': report['report']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='Audio paths or a folder; duplicate entries are retained')
    parser.add_argument('--method', choices=('ml', 'baseline'), default='ml')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--contextual', action='store_true', help='Use musical timelines to choose validated cue/recipe candidates')
    parser.add_argument('--excerpt-seconds', type=float, default=180)
    parser.add_argument('--preview-join', type=int)
    parser.add_argument('--preview-best', action='store_true', help='Try up to three compatible planned joins')
    args = parser.parse_args()
    settings = Settings.from_env()
    storage = Storage(settings.data_root)
    storage.initialize()
    entries = collect_entries(discover(args.inputs), settings, storage)
    print('Fitting library similarity and pair groups...', flush=True)
    learned = fit_library(entries)
    plan, details = build_plan(entries, uuid4().hex, args.method, args.excerpt_seconds, learned)
    if args.contextual:
        from backend.app.planning.contextual_set import contextualize_plan
        plan, details = contextualize_plan(entries, plan, details, settings, storage)
    data_hash = hashlib.sha256((VERSION+':'+':'.join(learned['model']['training_content_hashes'])).encode()).hexdigest()
    model_path = storage.path('models', 'library-'+data_hash+'.json')
    model_path.write_text(json.dumps(learned['model'], indent=2, allow_nan=False), encoding='utf-8')
    artifact = {'plan': json.loads(plan.to_json()), 'planning': details, 'model_path': str(model_path),
                'model_version': VERSION, 'preview_attempts': []}
    if args.compare:
        other = 'baseline' if args.method == 'ml' else 'ml'
        comparison, comparison_details = build_plan(entries, plan.mix_id, other, args.excerpt_seconds, learned)
        artifact['comparison'] = {'plan': json.loads(comparison.to_json()), 'planning': comparison_details,
                                  'note': 'Diagnostic comparison, not a measured listening-quality improvement.'}
    persist_plan(entries, plan, settings)
    artifact_path = storage.path('plans', 'mix-'+plan.mix_id+'.json')
    artifact_path.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding='utf-8')
    summary_path = artifact_path.with_suffix('.md')
    write_summary(summary_path, artifact)
    print(f'Plan: {artifact_path}\nModel: {model_path}', flush=True)
    print(f'Summary: {summary_path}', flush=True)
    print('Transitions:', json.dumps(details['diagnostics']), flush=True)
    names = {entry['entry_id']: Path(entry['path']).name for entry in entries}
    for i, excerpt in enumerate(plan.excerpts):
        suffix = f' -> {plan.transitions[i].bars} bars / {plan.transitions[i].style}' if i < len(plan.transitions) else ''
        print(f'{i+1:02d}. {names[excerpt.track_id]} [{excerpt.source_in:.1f}-{excerpt.source_out:.1f}s]{suffix}', flush=True)
    if args.preview_join or args.preview_best:
        candidates = [args.preview_join] if args.preview_join else sorted(
            [i+1 for i, t in enumerate(plan.transitions) if t.bars],
            key=lambda j: (-plan.transitions[j-1].bars, details['joins'][j-1]['learned_distance'], j))[:3]
        for join in candidates:
            try:
                result = preview_join(entries, plan, details, settings, storage, join)
                artifact['preview_attempts'].append({'join': join, 'status': 'succeeded', **result})
                break
            except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
                artifact['preview_attempts'].append({'join': join, 'status': 'failed', 'reason': str(exc)})
                print(f'Join {join} needs review: {exc}', flush=True)
        artifact_path.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding='utf-8')
        write_summary(summary_path, artifact)
        if not any(attempt['status'] == 'succeeded' for attempt in artifact['preview_attempts']):
            raise ValueError(f'No requested audition passed audio validation; saved plan remains available at {artifact_path}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Cannot plan mix: {exc}', file=sys.stderr)
        raise SystemExit(1)
