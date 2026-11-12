"""Compare independently detected beat markers without hiding unmatched beats."""
import numpy as np

VERSION='independent-beat-bar-gate-1'


def marker_alignment(first,second,start,end,tolerance=.025):
    if not np.isfinite([start,end,tolerance]).all() or end<=start or tolerance<=0:
        raise ValueError('Invalid marker comparison window')
    a=np.asarray(first,dtype=float);b=np.asarray(second,dtype=float)
    if a.ndim!=1 or b.ndim!=1 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Invalid beat marker arrays')
    if np.any(np.diff(a)<=0) or np.any(np.diff(b)<=0):
        raise ValueError('Beat markers must be strictly increasing')
    a=a[(a>=start)&(a<=end)];b=b[(b>=start)&(b<=end)]
    if len(a)<3 or len(b)<3:return {'status':'unknown','reason':'Insufficient independently detected markers'}
    distance=abs(a[:,None]-b[None,:])
    nearest_a=distance.min(axis=1);nearest_b=distance.min(axis=0)
    offsets=b[np.argmin(distance,axis=1)]-a
    coverage=min(float(np.mean(nearest_a<=tolerance)),float(np.mean(nearest_b<=tolerance)))
    return {'status':'aligned' if coverage>=.9 else 'mismatch',
            'outgoing_count':len(a),'incoming_count':len(b),'matched_fraction':coverage,
            'median_incoming_offset_seconds':float(np.median(offsets)),
            'p90_absolute_offset_seconds':float(np.percentile(np.r_[nearest_a,nearest_b],90)),
            'tolerance_seconds':tolerance}


def bar_support(beats,downbeats,start,end):
    beats=np.asarray(beats,dtype=float);downs=np.asarray(downbeats,dtype=float)
    counts=[]
    for left,right in zip(downs,downs[1:]):
        if left<start or right>end:continue
        counts.append(int(np.sum((beats>=left-.05)&(beats<right-.05))))
    if len(counts)<3:return {'status':'unknown','reason':'Fewer than three complete bars','beat_counts':counts}
    return {'status':'regular' if all(count==4 for count in counts) else 'unknown',
            'beat_counts':counts,'reason':'Independent predicted 4/4 bar support; phrase alignment remains unverified'}


def require_alignment(audit):
    """Fail closed on missing, unstable or conflicting musical markers."""
    if (audit.get('beats',{}).get('status')!='aligned'
            or audit.get('downbeats',{}).get('status')!='aligned'
            or len(audit.get('bar_support',[]))!=2
            or any(item.get('status')!='regular' for item in audit['bar_support'])):
        raise ValueError('Independent beat/bar timing is mismatched or uncertain; preview publication blocked')


def window_alignment(first, second, start, end, tolerance=.025):
    """Match core markers against neighbors across a query edge, symmetrically.

    A 20ms detection difference can straddle a local-window boundary. Keep every
    core marker accountable but allow its actual match just outside that window;
    never erase unmatched core markers or increase the declared tolerance.
    """
    marker_alignment(first, second, start, end, tolerance)  # validate full sequences
    all_a, all_b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    a, b = all_a[(all_a>=start)&(all_a<=end)], all_b[(all_b>=start)&(all_b<=end)]
    if len(a)<3 or len(b)<3:
        return {'status':'unknown','reason':'Insufficient independently detected local markers'}
    neighbors_a = all_a[(all_a>=start-tolerance)&(all_a<=end+tolerance)]
    neighbors_b = all_b[(all_b>=start-tolerance)&(all_b<=end+tolerance)]
    distance_a, distance_b = abs(a[:,None]-neighbors_b[None,:]), abs(b[:,None]-neighbors_a[None,:])
    nearest_a, nearest_b = distance_a.min(axis=1), distance_b.min(axis=1)
    offsets = neighbors_b[np.argmin(distance_a,axis=1)]-a
    coverage = min(float(np.mean(nearest_a<=tolerance)),float(np.mean(nearest_b<=tolerance)))
    return {'status':'aligned' if coverage>=.9 else 'mismatch', 'outgoing_count':len(a), 'incoming_count':len(b),
        'matched_fraction':coverage, 'median_incoming_offset_seconds':float(np.median(offsets)),
        'p90_absolute_offset_seconds':float(np.percentile(np.r_[nearest_a,nearest_b],90)),
        'tolerance_seconds':tolerance, 'edge_policy':'Every core marker matched symmetrically; neighbors within tolerance retained'}


def clock_alignment(first,second,start,end,tolerance=.025):
    """Resolve detector-frame jitter only with complete, regular observed clocks.

    BeatThis timestamps have 20ms resolution. Retain the raw check and require
    fitted phase at both window edges within the original physical tolerance.
    Missing events, irregular timing, real phase errors and drift still fail.
    """
    raw=window_alignment(first,second,start,end,tolerance)
    if raw['status']!='mismatch':return raw
    a,b=np.asarray(first),np.asarray(second)
    fits=[]
    for one,two in ((a,b),(b,a)):
        core=one[(one>=start)&(one<=end)]
        nearest=np.argmin(abs(core[:,None]-two[None,:]),axis=1)
        matches=two[nearest]
        if len(set(nearest))!=len(core) or np.max(abs(matches-core))>tolerance+.021:return raw
        x=np.arange(len(core));p,o=np.polyfit(x,core,1);q,v=np.polyfit(x,matches,1)
        residuals=[float(np.max(abs(core-(p*x+o)))),float(np.max(abs(matches-(q*x+v))))]
        phase=(q-p)*(np.array([start,end])-o)/p+v-o
        if not (.4<p<.6 and .4<q<.6) or max(residuals)>.026 or np.max(abs(phase))>tolerance:return raw
        fits.append({'edge_phase_seconds':phase.tolist(),'maximum_residual_seconds':residuals,
                     'observed_period_seconds':[float(p),float(q)],'count':len(core)})
    return {**raw,'status':'aligned','verification':'quantization-aware-clock-fit-1',
            'raw_marker_check':raw,'clock_fits':fits,'detector_frame_seconds':.02}


def contextual_bar_support(beats,downbeats,start,end):
    """Use the nearest observed bars when a short handoff has few complete bars."""
    core=bar_support(beats,downbeats,start,end)
    if len(core.get('beat_counts',[]))>=3:return core
    b=np.asarray(beats);d=np.asarray(downbeats)
    rows=[(float(left),float(right),int(np.sum((b>=left-.05)&(b<right-.05))))
          for left,right in zip(d,d[1:])]
    if len(rows)<3:return core
    middle=(start+end)/2
    nearest=sorted(rows,key=lambda r:abs((r[0]+r[1])/2-middle))[:3]
    selected=sorted(set(nearest+[r for r in rows if r[0]>=start and r[1]<=end]))
    return {'status':'regular' if all(r[2]==4 for r in selected) else 'unknown',
            'beat_counts':[r[2] for r in selected], 'support_window':[selected[0][0],selected[-1][1]],
            'reason':'Nearest independently observed context bars plus every complete overlap bar'}


def audit_join(first, second, expected, entry, end, encoded=None, *, manual=False):
    """Compare actual independent detections, original mappings and local halves."""
    windows = [('whole', entry+.5, end-.5), ('early', entry+.5, (entry+end)/2),
               ('late', (entry+end)/2, end-.5)]
    checks = []
    def compare(a,b,left,right,tolerance,kind,window,comparison):
        comparator=clock_alignment if manual and kind=='beats' else window_alignment
        result=comparator(a,b,left,right,tolerance)
        if manual and kind=='downbeats' and window!='whole' and result['status']=='unknown':
            beat=next((c for c in checks if c['window']==window and c['kind']=='beats' and c['comparison']==comparison),None)
            whole=window_alignment(a,b,entry+.5,end-.5,tolerance)
            if beat and beat['status']=='aligned' and whole['status']=='aligned':
                return {**whole,'local_status':'unknown','verification':'whole-overlap bar phase plus aligned local beats',
                        'reason':'This half has too few downbeats; bar phase is verified over the complete overlap'}
        return result
    for name, left, right in windows:
        for kind, tolerance in (('beats', .025), ('downbeats', .07)):
            result = compare(first[kind], second[kind], left, right, tolerance,kind,name,'prepared_pair')
            checks.append({'window': name, 'kind': kind, 'comparison': 'prepared_pair', **result})
            for side, observed in enumerate((first, second)):
                checks.append({'window': name, 'kind': kind, 'comparison': f'original_mapping_{side}',
                    **compare(expected[side][kind], observed[kind], left, right, tolerance,kind,name,f'original_mapping_{side}')})
            if encoded is not None:
                for side, observed in enumerate((first, second)):
                    checks.append({'window': name, 'kind': kind, 'comparison': f'encoded_overlap_{side}',
                        **compare(observed[kind], encoded[kind], left, right, tolerance,kind,name,f'encoded_overlap_{side}')})
    support_function=contextual_bar_support if manual else bar_support
    support = [support_function(item['beats'], item['downbeats'], entry+.5, end-.5) for item in (first, second)]
    return {'version': VERSION, 'checks': checks, 'bar_support': support,
            'status': 'validated' if all(check['status'] == 'aligned' for check in checks)
                and all(item['status'] == 'regular' for item in support) else 'needs_review'}


def recheck_original_grid(audit, observed, expected, originals, entry, end):
    """Resolve cached-context disagreement only with fully accountable originals.

    Original failed measurements remain unchanged. The worker must provide both
    raw and preparation-gain local detections from verified source audio.
    """
    from copy import deepcopy
    failed = [c for c in audit['checks'] if c['status'] != 'aligned']
    if (not failed or any(c['status'] != 'mismatch' or c['comparison'] not in
                         ('original_mapping_0', 'original_mapping_1') for c in failed)
            or len(audit.get('solo_checks', [])) != 2 or len(audit['bar_support']) != 2
            or any(c['status'] != 'aligned' for c in audit.get('solo_checks', []))
            or any(s['status'] != 'regular' for s in audit['bar_support'])):
        return audit
    sides = {int(c['comparison'][-1]) for c in failed}
    result = deepcopy(audit)
    checks, support = [], []
    windows = [('whole', entry+.5, end-.5), ('early', entry+.5, (entry+end)/2),
               ('late', (entry+end)/2, end-.5)]
    for side in sorted(sides):
        variants = originals.get(side, {})
        if set(variants) != {'raw', 'prepared_gain'}:
            return audit
        for variant, local in variants.items():
            support.append({'side': side, 'variant': variant,
                **bar_support(local['beats'], local['downbeats'], entry+.5, end-.5)})
            for window, left, right in windows:
                for kind, tolerance in (('beats', .025), ('downbeats', .07)):
                    checks.append({'side': side, 'variant': variant, 'window': window, 'kind': kind,
                        'comparison': 'local_original_to_prepared',
                        **window_alignment(local[kind], observed[side][kind], left, right, tolerance)})
                    cached = window_alignment(expected[side][kind], local[kind], left, right, tolerance)
                    checks.append({'side': side, 'variant': variant, 'window': window, 'kind': kind,
                        'comparison': 'cached_to_local_original', 'required_coverage': 1., **cached})
    resolved = (all(c['status'] == 'aligned' and (c['comparison'] != 'cached_to_local_original'
                    or c['matched_fraction'] == 1.) for c in checks)
                and all(s['status'] == 'regular' for s in support))
    result['original_context_recheck'] = {'policy': 'same-context-original-1', 'checks': checks,
        'bar_support': support, 'status': 'validated' if resolved else 'needs_review',
        'detected_originals': originals}
    if resolved:
        for check in result['checks']:
            if check['status'] != 'aligned':
                check['resolved_by'] = 'same-context-original-1'
        result.update(status='validated', version='independent-beat-bar-gate-2')
    return result


