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


def audit_join(first, second, expected, entry, end, encoded=None):
    """Compare actual independent detections, original mappings and local halves."""
    windows = [('whole', entry+.5, end-.5), ('early', entry+.5, (entry+end)/2),
               ('late', (entry+end)/2, end-.5)]
    checks = []
    for name, left, right in windows:
        for kind, tolerance in (('beats', .025), ('downbeats', .07)):
            result = window_alignment(first[kind], second[kind], left, right, tolerance)
            checks.append({'window': name, 'kind': kind, 'comparison': 'prepared_pair', **result})
            for side, observed in enumerate((first, second)):
                checks.append({'window': name, 'kind': kind, 'comparison': f'original_mapping_{side}',
                    **window_alignment(expected[side][kind], observed[kind], left, right, tolerance)})
            if encoded is not None:
                for side, observed in enumerate((first, second)):
                    checks.append({'window': name, 'kind': kind, 'comparison': f'encoded_overlap_{side}',
                        **window_alignment(observed[kind], encoded[kind], left, right, tolerance)})
    support = [bar_support(item['beats'], item['downbeats'], entry+.5, end-.5) for item in (first, second)]
    return {'version': VERSION, 'checks': checks, 'bar_support': support,
            'status': 'validated' if all(check['status'] == 'aligned' for check in checks)
                and all(item['status'] == 'regular' for item in support) else 'needs_review'}


