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


def detect_prepared_alignment(paths,start,end,models):
    """Measure exact prepared waveforms using the already pinned CPU model."""
    from pathlib import Path
    import soundfile as sf
    import torch
    from beat_this.inference import Audio2Beats
    from scripts.setup_dj_benchmarks import digest
    checkpoint=Path(models)/'final0.ckpt'
    expected='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
    if digest(checkpoint)!=expected:raise ValueError('Pinned beat checkpoint changed')
    torch.set_num_threads(4)
    tracker=Audio2Beats(checkpoint_path=str(checkpoint),device='cpu',dbn=False)
    sources=[]
    for path in paths:
        samples,rate=sf.read(path,dtype='float32')
        with torch.inference_mode():beats,downs=tracker(samples,rate)
        sources.append({'prepared_sha256':digest(path),'beats':list(map(float,beats)),
                        'downbeats':list(map(float,downs))})
    if len(sources)!=2:raise ValueError('Timing gate requires two prepared sources')
    # Ignore a short entrance/exit boundary, retain actual overlap body.
    left,right=start+1,end-1
    result={'version':VERSION,'checkpoint_sha256':expected,'sources':sources,
            'beats':marker_alignment(sources[0]['beats'],sources[1]['beats'],left,right,.025),
            'downbeats':marker_alignment(sources[0]['downbeats'],sources[1]['downbeats'],left,right,.07),
            'bar_support':[bar_support(source['beats'],source['downbeats'],left,right) for source in sources],
            'phrase_alignment':'unverified','listening_accepted':None}
    try:require_alignment(result)
    except ValueError:result['publication_allowed']=False
    else:result['publication_allowed']=True
    return result
