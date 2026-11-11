"""Local, abstaining spectral attribution; estimates are never human reviews."""
import hashlib
import numpy as np
from scipy.ndimage import uniform_filter1d, median_filter
from .timelines import canonical
from scripts.setup_timeline import sha256
from pathlib import Path

VERSION = 'transition-magnitude-context-3'
LIMITATIONS = ('Spectral magnitude approximation; confidence is heuristic, not calibrated. '
               'Cannot identify exact mixer controls, vocals, echoes or filters. '
               'Different edits, pitch changes, extra tracks or inaccurate source cues can prevent attribution.')
BANDS = {'bass': slice(0, 11), 'mids': slice(11, 24), 'upper': slice(24, 32)}


def fit_gains(a, b, mix):
    """Vectorized exact two-variable nonnegative least squares, one row per time."""
    aa, bb, ab = (np.sum(v, axis=1) for v in (a*a, b*b, a*b))
    ay, by = np.sum(a*mix, axis=1), np.sum(b*mix, axis=1)
    determinant = aa*bb-ab*ab
    g = np.column_stack(((ay*bb-by*ab)/np.maximum(determinant, 1e-20),
                         (by*aa-ay*ab)/np.maximum(determinant, 1e-20)))
    edge_a = np.column_stack((ay/np.maximum(aa, 1e-20), np.zeros(len(a))))
    edge_b = np.column_stack((np.zeros(len(a)), by/np.maximum(bb, 1e-20)))
    candidates = np.stack((np.maximum(g, 0), edge_a, edge_b), axis=1)
    residual = mix[:, None, :]-candidates[:, :, :1]*a[:, None, :]-candidates[:, :, 1:]*b[:, None, :]
    errors = np.sum(residual**2, axis=2)
    chosen = errors.argmin(axis=1)
    gains = candidates[np.arange(len(a)), chosen]
    relative = np.sqrt(errors[np.arange(len(a)), chosen]/np.maximum(np.sum(mix*mix, axis=1), 1e-20))
    separation = 1-ab/np.sqrt(np.maximum(aa*bb, 1e-20))
    return gains, relative, separation


def attribute_interval(recording, outgoing, incoming, decision, marked_interval=None):
    """Fit linear magnitudes; power additivity breaks on phase-locked bass."""
    start, end = decision['mix_start'], decision['mix_end']
    duration = end-start
    rates = [(decision[p+'_source_out']-decision[p+'_source_in'])/duration if duration else None
             for p in ('outgoing','incoming')]
    if duration and any(not .9 <= rate <= 1.1 for rate in rates):
        return {'technique':'unknown','confidence':'insufficient','recipe':None,
                'description':f'The recording overlap lasts {duration:.1f} seconds, but the original-song cue intervals imply '
                              'a tempo change greater than 10%. Check both original-song cues before analyzing again.',
                'curves':[],'quality':{'source_playback_rates':rates}}
    if not 2 <= duration <= 128:
        return {'technique': 'unknown', 'confidence': 'insufficient', 'recipe': None,
                'description': 'This interval is too short or too long for reliable spectral attribution. '
                               'A short interval alone does not establish a cut.', 'curves': [], 'quality': {}}
    for array in (recording, outgoing, incoming):
        if array.ndim != 2 or array.shape[1] != 32 or not np.isfinite(array).all():
            raise ValueError('Invalid spectral analysis features')
    times = np.arange(start+.5, end-.5, .25)
    def sample(values, locations):
        # Feature timestamps are starts of 256 ms windows.
        indices = (locations-.128)*4
        if indices.min() < 0 or indices.max() > len(values)-1:
            raise ValueError('Source cues extend beyond available spectral evidence')
        return np.column_stack([np.interp(indices, np.arange(len(values)), values[:, band]) for band in range(32)])
    mix = sample(recording, times)
    locations = [decision[p+'_source_in']+(times-start)/duration*(decision[p+'_source_out']-decision[p+'_source_in'])
                 for p in ('outgoing', 'incoming')]
    # One shared scale prevents overflow while preserving relative source levels.
    offset = float(max(mix.max(), outgoing.max(), incoming.max()))
    y = uniform_filter1d(np.exp(.5*(mix-offset)), size=5, axis=0, mode='nearest')
    weight = 1/np.maximum(y.mean(axis=0), max(float(y.max())*1e-4, 1e-20))
    y *= weight
    options = []
    for values, points in zip((outgoing, incoming), locations):
        candidates = []
        for shift in np.arange(-1., 1.01, .25):
            try:
                spectrum = sample(values, points+shift)
            except ValueError:
                continue
            candidates.append((float(shift), uniform_filter1d(np.exp(.5*(spectrum-offset)), size=5, axis=0, mode='nearest')*weight))
        if not candidates:
            raise ValueError('Source cues extend beyond available spectral evidence')
        options.append(candidates)
    best = None
    for shift_a, a in options[0]:
        for shift_b, b in options[1]:
            _, error, _ = fit_gains(a, b, y)
            score = float(np.median(error))+.005*(abs(shift_a)+abs(shift_b))
            if best is None or score < best[0]:
                best = (score, shift_a, shift_b, a, b)
    _, shift_a, shift_b, a, b = best
    curves, errors, separations, gains = [], [], [], []
    for band in BANDS.values():
        g, error, separation = fit_gains(a[:, band], b[:, band], y[:, band])
        gains.append(median_filter(g, size=(5, 1), mode='nearest'))
        errors.append(error); separations.append(separation)
    gains = np.stack(gains, axis=1)  # time, band, source
    scales = np.maximum(np.percentile(gains, 90, axis=(0, 1)), 1e-8)
    gains = np.clip(gains/scales[None, None, :], 0, 2)
    residual = float(np.median(errors))
    identifiable = float(np.mean(np.array(separations) > .08))
    audible = [float(np.mean(gains[:, :, i].mean(axis=1) > .15)) for i in (0, 1)]
    supported = residual < .28 and identifiable > .65 and min(audible) > .15
    high = supported and residual < .18 and identifiable > .8 and max(abs(shift_a), abs(shift_b)) < 1
    confidence = 'high' if high else 'moderate' if supported else 'insufficient'
    # A fixed boundary window sees a hard exit; a whole-overlap fraction can
    # span many seconds and hide it even when post-exit context is available.
    count = max(2, min(len(times)//5, 4))
    early, late = np.median(gains[:count], axis=0), np.median(gains[-count:], axis=0)
    outgoing_fades = float(np.mean(early[:, 0]-late[:, 0])) > .25
    incoming_rises = float(np.mean(late[:, 1]-early[:, 1])) > .25
    # Relative bass and mid/upper handoff timing distinguishes EQ from full-band fades.
    crossings = []
    for band in range(3):
        share = gains[:, band, 1]/np.maximum(gains[:, band].sum(axis=1), 1e-8)
        crossing = np.flatnonzero((share[:-1] < .5) & (share[1:] >= .5))
        crossings.append(float((times[crossing[0]]-start)/duration) if len(crossing) else None)
    eq = (all(c is not None for c in crossings) and max(crossings)-min(crossings) > .15
          and outgoing_fades and incoming_rises)
    technique = ('eq_handoff' if eq else 'gradual_blend' if outgoing_fades and incoming_rises else 'unknown') if supported else 'unknown'
    if technique == 'eq_handoff':
        description = 'Bass and mid/upper frequencies change hands at different times, suggesting an EQ handoff. '
    elif technique == 'gradual_blend':
        description = 'The outgoing song fades down while the incoming song rises across the measured frequency bands. '
    elif supported:
        description = 'Both originals can be attributed, but the measured changes do not clearly match a supported technique. '
    else:
        description = 'The recording cannot be explained reliably by these two aligned originals. Check source cues and song versions. '
    marked_start,marked_end=marked_interval or (start,end)
    description += f'The marked overlap lasts {marked_end-marked_start:.1f} seconds.'
    if supported and all(c is not None for c in crossings):
        description += (f' Incoming bass becomes stronger than outgoing bass about {start+crossings[0]*duration-marked_start:.1f} seconds from entry; '
                        f'mids change predominance at about {start+crossings[1]*duration-marked_start:.1f} seconds and upper frequencies at {start+crossings[2]*duration-marked_start:.1f} seconds.')
    observations=[]
    if supported:
        for j,band in enumerate(BANDS):
            parts=[]
            for source,i in (('Outgoing',0),('incoming',1)):
                delta=float(late[j,i]-early[j,i])
                verb='rises' if delta>.2 else 'fades down' if delta<-.2 else 'stays near its earlier level'
                parts.append(f'{source} {band} {verb}')
            observations.append('; '.join(parts)+'.')
    for i in range(0, len(times), 2):
        curves.append({'seconds': float(times[i]), **{name: gains[i, j].tolist() for j, name in enumerate(BANDS)}})
    return {'technique': technique, 'confidence': confidence, 'recipe': None, 'description': description,
            'quality': {'relative_spectral_error': residual, 'identifiable_fraction': identifiable,
                        'source_playback_rates':rates,
                        'analysis_interval_seconds':[start,end],
                        'marked_interval_seconds':[marked_start,marked_end],
                        'band_relative_errors':dict(zip(BANDS,[float(np.median(e)) for e in errors])),
                        'source_audible_fractions': audible, 'offset_refinement_seconds': [shift_a, shift_b]},
            'handoff_seconds_from_entry': dict(zip(BANDS, [start+c*duration-marked_start if c is not None else None for c in crossings])),
            'observations':observations,
            'curves': curves}


def attribute(recording, outgoing, incoming, decision):
    duration=decision['mix_end']-decision['mix_start']
    if duration > .5:
        if not 2<=duration<=124:
            return attribute_interval(recording,outgoing,incoming,decision)
        rates=[(decision[p+'_source_out']-decision[p+'_source_in'])/duration for p in ('outgoing','incoming')]
        if any(not .9<=rate<=1.1 for rate in rates):
            return attribute_interval(recording,outgoing,incoming,decision)
        # Observe silence/presence just outside the listener's boundaries too.
        # Extrapolate only within actual available source audio; do not edit cues.
        before=max(0,min(2.,decision['mix_start'],*[decision[p+'_source_in']/r for p,r in zip(('outgoing','incoming'),rates)]))
        after=max(0,min(2.,len(recording)/4-.5-decision['mix_end'],
            *[(len(f)/4-.5-decision[p+'_source_out'])/r for p,r,f in zip(('outgoing','incoming'),rates,(outgoing,incoming))]))
        extended=dict(decision,mix_start=decision['mix_start']-before,mix_end=decision['mix_end']+after)
        for prefix,rate in zip(('outgoing','incoming'),rates):
            extended[prefix+'_source_in']-=before*rate
            extended[prefix+'_source_out']+=after*rate
        return attribute_interval(recording,outgoing,incoming,extended,(decision['mix_start'],decision['mix_end']))
    # A marked zero-length handoff is not sufficient: inspect actual source
    # dominance either side. This context does not change any reviewed cue.
    extended=dict(decision)
    extended['mix_start']-=2.5;extended['mix_end']+=2.5
    for prefix in ('outgoing','incoming'):
        extended[prefix+'_source_in']-=2.5
        extended[prefix+'_source_out']+=2.5
    if min(extended[k] for k in ('mix_start','outgoing_source_in','incoming_source_in'))<0:
        return {'technique':'unknown','confidence':'insufficient','recipe':None,'curves':[],'quality':{},
                'description':'Not enough audio before the marked handoff to verify a cut.'}
    try:
        result=attribute_interval(recording,outgoing,incoming,extended)
    except ValueError:
        return {'technique':'unknown','confidence':'insufficient','recipe':None,'curves':[],'quality':{},
                'description':'Not enough original-song audio around the marked handoff to verify a cut.'}
    curve=result['curves']
    if not curve:
        return result
    shares=np.array([np.array([row[b] for b in BANDS]).mean(axis=0) for row in curve])
    share=shares[:,1]/np.maximum(shares.sum(axis=1),1e-8)
    early=np.flatnonzero(share<=.25);late=np.flatnonzero(share>=.75)
    cut=False
    if len(early) and len(late) and result['confidence']=='high':
        left,right=curve[int(early[-1])]['seconds'],curve[int(late[0])]['seconds']
        cut=0<right-left<=1.5 and abs((left+right)/2-(decision['mix_start']+decision['mix_end'])/2)<=.75
    result['technique']='cut' if cut else 'unknown'
    result['description']=('The outgoing original dominates before the marked handoff and the incoming original immediately afterward. '
                           'The measured switch supports a cut.' if cut else
                           'The audio around this short marked interval does not reliably establish an abrupt source switch. Style stays unknown.')
    result['quality']['cut_context_seconds']=2.5
    return result


def map_recipe(result, duration, bars):
    """Renderer categories include duration; technique alone cannot supply one."""
    result['overlap_bars_estimate'] = bars
    if result['technique']=='cut' and result['confidence']=='high':
        result['recipe']='cut'
    if bars is not None and result['confidence'] == 'high':
        if result['technique'] == 'eq_handoff' and abs(bars-8) <= 1:
            result['recipe'] = 'eq_8'
        elif result['technique'] == 'gradual_blend':
            if abs(bars-16) <= 2:
                result['recipe'] = 'controlled_16'
            elif abs(bars-32) <= 3:
                result['recipe'] = 'groove_32'
    result['training_eligible'] = result['recipe'] is not None
    result['description'] += (' Supported renderer style: '+result['recipe']+'.' if result['recipe'] else
                              ' No supported renderer style label is assigned; style training stays unknown.')
    return result


def analyze_snapshot(snapshot, references, progress=None, live=None):
    if snapshot.get('algorithm_version',VERSION)!=VERSION:
        raise ValueError('The analyzer changed. Open the updated app and start a new analysis.')
    imported = references.get(snapshot['reference_id'])['import']
    if imported['recording']['content_hash'] != snapshot['recording_hash']:
        raise ValueError('Reference recording identity changed')
    recording = references._features(imported['recording'])
    results = []
    for index, example in enumerate(snapshot['examples']):
        if live and not live():
            raise ValueError('Analysis cancelled or worker lease lost')
        if progress:
            progress(f'Analyzing transition {index+1} of {len(snapshot["examples"])}', .05+.85*index/len(snapshot['examples']))
        decision = example['decision']
        sources = example['sources']
        features = [references._features(s) for s in sources]
        result = attribute(recording, *features, decision)
        duration = decision['mix_end']-decision['mix_start']
        bars = decision.get('overlap_bars')
        tempo = None
        if bars is None and duration >= 2 and result['technique'] != 'unknown':
            from .audio.analyze import analyze
            from .planning.rhythm import analyze_rhythm
            analysis = analyze(Path(sources[1]['path']), references.settings, references.storage)
            rhythm = analyze_rhythm(Path(sources[1]['path']), analysis, references.settings, references.storage)
            if rhythm.get('reliable') and rhythm.get('confidence', 0) >= .65 and rhythm.get('bpm'):
                tempo = rhythm['bpm']*(decision['incoming_source_out']-decision['incoming_source_in'])/duration
                bars = duration*tempo/240
        result = map_recipe(result, duration, bars)
        result.update(position=example['position'], review_revision=example['review_revision'],
                      algorithm_version=VERSION, source_hashes=[s['content_hash'] for s in sources],
                      implementation_hash=sha256(Path(__file__)), feature_version='reference-spectral-1',
                      recording_hash=snapshot['recording_hash'], decision_hash=hashlib.sha256(canonical(decision).encode()).hexdigest(),
                      tempo_estimate=tempo, limitations=LIMITATIONS,
                      label_origin='automatic_spectral_estimate', human_confirmed=False)
        results.append(result)
    # Recheck all bytes before publication, including sources reused from caches.
    for source in [imported['recording']]+[s for e in snapshot['examples'] for s in e['sources']]:
        if sha256(Path(source['path'])) != source['content_hash']:
            raise ValueError('Audio changed during transition analysis')
    recognized=sum(r['technique']!='unknown' for r in results)
    return {'analyses': results, 'algorithm_version': VERSION, 'draft_id': snapshot['draft_id'],
            'summary':{'processed':len(results),'recognized':recognized,
                       'training_labels':sum(r['training_eligible'] for r in results),
                       'uncertain':len(results)-recognized}}
