"""Research compatibility wrapper for shared independent beat/bar validation."""
from backend.app.audio.beat_validation import VERSION, marker_alignment, bar_support, require_alignment


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
