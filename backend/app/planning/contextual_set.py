"""Opt-in contextual choices layered onto a complete conservative set plan."""
from copy import deepcopy
from dataclasses import replace
import json
from backend.app.auditions import evaluate_pair
from backend.app.models import MixPlan
from backend.app.timelines import TimelineStore
from .contextual import propose_pair, VERSION


def contextualize_plan(entries, plan, details, settings, storage):
    lookup = {e['entry_id']: e for e in entries}
    if set(lookup) != {e.track_id for e in plan.excerpts}:
        raise ValueError('Contextual planning requires every original input entry')
    store = TimelineStore(storage.root)
    working = plan
    result = deepcopy(details)
    joins = []
    for i in range(len(plan.transitions)):
        first, second = working.excerpts[i:i+2]
        provenance = {'selected': None, 'fallback': None}
        joins.append(provenance)
        if abs(first.target_bpm-second.target_bpm) > 1e-6:
            provenance['fallback'] = 'No shared target tempo; conservative join retained'
            continue
        records, sources = [], {}
        try:
            for cue in (first, second):
                entry = lookup[cue.track_id]
                record = store.for_content(entry['analysis']['content_hash'])
                record['track_id'] = cue.track_id
                records.append(record)
                sources[cue.track_id] = entry['path']
        except KeyError:
            provenance['fallback'] = 'Missing musical timeline; conservative join retained'
            continue
        transition = working.transitions[i]
        preferred = (first.source_out-transition.overlap_seconds/2*first.target_bpm/first.source_bpm,
                     second.source_in+transition.overlap_seconds/2*second.target_bpm/second.source_bpm)
        batch = propose_pair(*records, bpms=(first.source_bpm, second.source_bpm), target_bpm=first.target_bpm, preferred=preferred)
        evaluation = evaluate_pair(batch, sources, settings, storage, audition_count=0)
        provenance['proposal_count'] = len(batch['candidates'])
        provenance['rejections'] = evaluation['rejections']
        for item in evaluation['validations']:
            candidate, validation = item['candidate'], item['validation']
            applied = MixPlan.from_json(json.dumps(validation['applied_plan']))
            a, b = applied.excerpts
            excerpts = list(working.excerpts)
            excerpts[i] = replace(first, source_out=a.source_out,
                                   source_in=min(first.source_in, a.source_in) if i == 0 else first.source_in)
            excerpts[i+1] = replace(second, source_in=b.source_in,
                                     source_out=max(second.source_out, b.source_out) if i+1 == len(excerpts)-1 else second.source_out)
            transitions = list(working.transitions)
            transitions[i] = applied.transitions[0]
            trial = replace(working, excerpts=tuple(excerpts), transitions=tuple(transitions))
            try:
                trial.validate()
            except ValueError as exc:
                provenance['rejections'].append({'candidate_id': candidate['id'], 'reason': str(exc), 'stage': 'set geometry'})
                continue
            working = trial
            provenance['selected'] = {'candidate_id': candidate['id'], 'recipe': candidate['recipe'],
                                      'context_score': candidate['context_score'], 'sources': candidate['sources'],
                                      'validation': validation}
            result['joins'][i].update(style=transitions[i].style, bars=transitions[i].bars, recipe=candidate['recipe'])
            break
        if provenance['selected'] is None:
            provenance['fallback'] = 'No contextual candidate passed waveform and set-geometry checks; conservative join retained'
    working.validate()
    result.setdefault('diagnostics', {}).update(
        long_transitions=sum(t.bars == 32 for t in working.transitions),
        controlled_transitions=sum(t.bars == 16 for t in working.transitions),
        short_transitions=sum(t.bars == 8 for t in working.transitions),
        phrase_cut_transitions=sum(t.style == 'phrase_cut' for t in working.transitions),
        boundary_transitions=sum(t.style == 'boundary_fade' for t in working.transitions))
    result['contextual'] = {'version': VERSION, 'joins': joins, 'selection_method': 'heuristic context baseline; no learned preference'}
    return working, result
