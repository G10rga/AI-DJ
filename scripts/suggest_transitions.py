"""Choose contextual cue/recipe candidates and render a real A/B audition."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from backend.app.audio.mdx import sha256_file
from backend.app.auditions import evaluate_pair
from backend.app.config import Settings
from backend.app.storage import Storage
from backend.app.timelines import TimelineStore
from backend.app.planning.contextual import propose_pair


def load_records(paths, settings, analyze_missing=False):
    store = TimelineStore(settings.data_root)
    records, sources = [], {}
    for i, source in enumerate(paths):
        source = Path(source).resolve(strict=True)
        digest = sha256_file(source)
        try:
            record = store.for_content(digest)
        except KeyError:
            if not analyze_missing:
                raise ValueError(f'No musical timeline for {source.name}; analyze it or use --analyze-missing')
            from backend.app.timeline_analysis import analyze_timeline
            analyze_timeline(source, settings, with_vocals=True)
            record = store.for_content(digest)
        # Uploaded entries, including duplicate audio, retain separate identities.
        record['track_id'] = f'{i}-'+record['track_id']
        records.append(record)
        sources[record['track_id']] = source
    return records, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outgoing', type=Path)
    parser.add_argument('incoming', type=Path)
    parser.add_argument('--analyze-missing', action='store_true')
    parser.add_argument('--render-count', type=int, choices=(0, 1, 2), default=2)
    parser.add_argument('--max-candidates', type=int, choices=range(1, 13), default=12)
    args = parser.parse_args()
    settings = Settings.from_env()
    storage = Storage(settings.data_root)
    storage.initialize()
    records, sources = load_records([args.outgoing, args.incoming], settings, args.analyze_missing)
    batch = propose_pair(*records, maximum=args.max_candidates)
    print(f'Proposed {len(batch["candidates"])} contextual candidates from {batch.get("pool_count",0)} screened choices', flush=True)
    result = evaluate_pair(batch, sources, settings, storage, audition_count=args.render_count)
    result['proposal_batch'] = batch
    name = 'context-pair-'+uuid4().hex
    report = storage.path('plans', name+'.json')
    report.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    lines = ['# Contextual transition comparison', '',
             f'{args.outgoing.name} -> {args.incoming.name}', '',
             f'{len(result["validations"])} waveform-valid proposals; {len(result["auditions"])} rendered auditions.',
             'Scores are a deterministic context baseline, not learned owner taste.', '']
    for i, audition in enumerate(result['auditions']):
        candidate = audition['requested_candidate']
        lines += [f'## Alternative {chr(65+i)}: {candidate["recipe"]}', '',
                  f'Audio: {audition["output"]}',
                  f'Source anchors: {candidate["anchors_seconds"]}; handoff at {audition["handoff_seconds"]:.2f}s.',
                  f'Context score: {candidate["context_score"]:.3f}; candidate {candidate["id"]}.', '']
        if audition.get('loudness'):
            lines += [f'Matched loudness: {audition["loudness"]["integrated_lufs"]:.2f} LUFS; true peak {audition["loudness"]["true_peak_dbfs"]:.2f} dBFS.', '']
    lines += ['## Limits', '', 'Waveform checks do not establish musical acceptance. No listening feedback has been recorded.',
              f'Full proposal/validation/rejection report: {report}', '']
    summary = report.with_suffix('.md')
    summary.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Report: {report}\nSummary: {summary}', flush=True)
    for audition in result['auditions']:
        print(f'{audition["requested_candidate"]["recipe"]}: {audition["output"]}', flush=True)
    if not result['validations'] or args.render_count and not result['auditions']:
        raise SystemExit('No requested candidate passed technical validation; see the saved rejection report')


if __name__ == '__main__':
    main()
