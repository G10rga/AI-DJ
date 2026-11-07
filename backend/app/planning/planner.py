"""Convert learned suggestions into a valid, complete MixPlan."""
from dataclasses import replace
import math
import numpy as np
from backend.app.models import MixPlan, Transition
from .excerpts import choose_excerpt
from .learning import fit_library
from .order import order_entries


def tempo_runs(entries):
    targets, runs = {}, []
    current, lower, upper = [], 0.0, float('inf')
    def flush():
        if not current:
            return
        tempos = [entries[i]['analysis']['rhythm']['bpm'] for i in current]
        target = float(np.clip(math.sqrt(min(tempos)*max(tempos)), lower, upper))
        runs.append({'entries': [entries[i]['entry_id'] for i in current], 'target_bpm': target})
        for i in current:
            targets[i] = target
    for index, entry in enumerate(entries):
        rhythm = entry['analysis'].get('rhythm', {})
        bpm = rhythm.get('bpm')
        if not rhythm.get('reliable') or not bpm:
            flush()
            current, lower, upper = [], 0.0, float('inf')
            targets[index] = float(bpm or 120)
            continue
        new_lower, new_upper = max(lower, bpm*.94), min(upper, bpm*1.06)
        if current and new_lower > new_upper:
            flush()
            current, lower, upper = [], 0.0, float('inf')
            new_lower, new_upper = bpm*.94, bpm*1.06
        current.append(index)
        lower, upper = new_lower, new_upper
    flush()
    return targets, runs


def build_plan(entries, mix_id, method='ml', requested_seconds=180.0, learned=None):
    if not entries or not math.isfinite(requested_seconds) or requested_seconds <= 0:
        raise ValueError('Provide tracks and a finite positive excerpt duration')
    for entry in entries:
        duration = entry['analysis']['audio']['duration']
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Invalid track duration')
    learned = fit_library(entries) if learned is None else learned
    route, objective = order_entries(entries, learned, method)
    ordered = [entries[i] for i in route]
    targets, runs = tempo_runs(ordered)
    transitions, explanations = [], []
    for position, (left, right) in enumerate(zip(route, route[1:])):
        a, b = ordered[position], ordered[position+1]
        ra, rb = a['analysis'].get('rhythm', {}), b['analysis'].get('rhythm', {})
        descriptor = learned['descriptors'][left, right]
        label = int(learned['pair_labels'][left, right])
        rank = learned['pair_rank'][label]
        long = rank == 0 if method == 'ml' else descriptor[1] < .06 and descriptor[2] < .35
        bars = 32 if long else 8
        warnings = ['Downbeat/phrase alignment and vocal compatibility require audio validation.']
        compatible = ra.get('reliable') and rb.get('reliable') and ra.get('bpm') and rb.get('bpm') and abs(targets[position]-targets[position+1]) < 1e-6
        if not compatible:
            transition = Transition('boundary_fade', .25, 0, tuple(warnings+['No shared reliable tempo run; no forced beatmatching.']))
        else:
            if descriptor[2] > .35 or descriptor[3] > 1:
                bars = 8
                warnings.append('Measured harmonic/energy contrast limits the overlap to eight bars.')
            transition = Transition('smooth' if bars == 32 else 'eq_cut', bars*4*60/targets[position], bars, tuple(warnings))
        transitions.append(transition)
        explanations.append({'from_entry': a['entry_id'], 'to_entry': b['entry_id'],
                             'pair_group': label if learned['model']['pair_model'] and method == 'ml' else None,
                             'pair_group_rank': rank, 'learned_suggestion_bars': 32 if long else 8,
                             'learned_distance': float(descriptor[0]), 'tempo_distance_octaves': float(descriptor[1]),
                             'chroma_distance': float(descriptor[2]), 'energy_distance_octaves': float(descriptor[3]),
                             'downgrades': []})
    def downgrade(index, reason):
        old = transitions[index]
        if old.style == 'boundary_fade':
            return False
        bars = 8 if old.bars == 32 else 0
        transitions[index] = Transition('eq_cut' if bars else 'boundary_fade',
                                        bars*4*60/targets[index] if bars else .25, bars,
                                        old.warnings+(reason,))
        explanations[index]['downgrades'].append(reason)
        return True
    for _ in range(2*len(transitions)+2):
        excerpts, cue_details = [], []
        for i, entry in enumerate(ordered):
            incoming = transitions[i-1].overlap_seconds if i else 0
            outgoing = transitions[i].overlap_seconds if i < len(transitions) else 0
            excerpt, details = choose_excerpt(entry, targets[i], requested_seconds, incoming, outgoing)
            excerpts.append(excerpt)
            cue_details.append(details)
        changed = False
        for i, excerpt in enumerate(excerpts):
            adjacent = ([i-1] if i else [])+([i] if i < len(transitions) else [])
            total = sum(transitions[j].overlap_seconds for j in adjacent)
            if total >= excerpt.output_duration-min(4*60/targets[i], excerpt.output_duration*.2):
                reducible = [j for j in adjacent if transitions[j].style != 'boundary_fade']
                if reducible:
                    worst = max(reducible, key=lambda j: (transitions[j].overlap_seconds, j))
                    changed |= downgrade(worst, 'Reduced overlap to preserve valid source bounds and a solo region.')
        for i, transition in enumerate(transitions):
            evidence = min(cue_details[i]['outgoing_support'], cue_details[i+1]['incoming_support'])
            required = .85 if transition.bars == 32 else .65
            if transition.style != 'boundary_fade' and evidence < required:
                changed |= downgrade(i, f'Regional pulse support {evidence:.2f} is insufficient for the proposed overlap.')
            if transition.style != 'boundary_fade':
                first_energy, second_energy = cue_details[i]['exit_energy'], cue_details[i+1]['entry_energy']
                contrast = abs(math.log2(max(first_energy, 1e-8)/max(second_energy, 1e-8)))
                if transition.bars == 32 and contrast > 1:
                    changed |= downgrade(i, 'Local entry/exit energy differs by over 6 dB; shorter overlap needs review.')
        if not changed:
            break
    else:
        raise RuntimeError('Transition geometry did not converge')
    plan = MixPlan(mix_id, 1, tuple(excerpts), tuple(transitions))
    plan.validate()
    if {excerpt.track_id for excerpt in plan.excerpts} != {entry['entry_id'] for entry in entries}:
        raise ValueError('Planner lost an uploaded entry')
    tracks = []
    for i, (entry, original) in enumerate(zip(ordered, route)):
        rhythm = entry['analysis'].get('rhythm', {})
        tracks.append({'entry_id': entry['entry_id'], 'path': entry['path'], 'content_hash': entry['analysis']['content_hash'],
                       'cluster': int(learned['track_labels'][original]),
                       'embedding': learned['embedding'][original].tolist(), 'estimated_bpm': rhythm.get('bpm'),
                       'rhythm_reliable': bool(rhythm.get('reliable')), 'cue_evidence': cue_details[i]})
    for i, detail in enumerate(explanations):
        detail.update(style=transitions[i].style, bars=transitions[i].bars,
                      recipe='long_groove' if transitions[i].bars == 32 else 'eq_swap' if transitions[i].bars else 'boundary_fade',
                      outgoing_support=cue_details[i]['outgoing_support'], incoming_support=cue_details[i+1]['incoming_support'])
    diagnostics = {'mean_tempo_distance': float(np.mean([x['tempo_distance_octaves'] for x in explanations])) if explanations else 0,
                   'mean_chroma_distance': float(np.mean([x['chroma_distance'] for x in explanations])) if explanations else 0,
                   'long_transitions': sum(t.bars == 32 for t in transitions),
                   'short_transitions': sum(t.bars == 8 for t in transitions),
                   'boundary_transitions': sum(t.style == 'boundary_fade' for t in transitions)}
    return plan, {'method': method, 'model': learned['model'], 'ordering_objective': objective, 'tracks': tracks, 'joins': explanations,
                  'tempo_runs': runs, 'diagnostics': diagnostics,
                  'limitations': ['Source cue support is approximate; every rendered pair still needs waveform phase checks.',
                                 'Unsupervised groups do not predict human acceptance or semantic vocal endings.']}


def change_transition(plan, index, style):
    if not 0 <= index < len(plan.transitions) or style not in {'smooth', 'eq_cut', 'boundary_fade'}:
        raise ValueError('Invalid transition change')
    transitions = list(plan.transitions)
    a, b = plan.excerpts[index:index+2]
    if style != 'boundary_fade' and plan.transitions[index].style == 'boundary_fade':
        raise ValueError('A boundary join requires fresh rhythm/cue validation before enabling beatmatching')
    if style != 'boundary_fade' and abs(a.target_bpm-b.target_bpm) > 1e-6:
        raise ValueError('Adjacent targets do not support a beatmatched handoff')
    bars = {'smooth': 32, 'eq_cut': 8, 'boundary_fade': 0}[style]
    transitions[index] = Transition(style, bars*4*60/a.target_bpm if bars else .25, bars,
                                     ('Transition changed; source cues and waveform phase require revalidation.',))
    updated = replace(plan, revision=plan.revision+1, transitions=tuple(transitions))
    updated.validate()
    return updated
