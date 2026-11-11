"""Continuous source playback with a protected outgoing line and gradual intro."""
import numpy as np

VERSION='vocal-continuity-handoff-1'


def envelopes(frames,rate,entry,fade_start,end,intro_level=.25):
    if not np.isfinite([frames,rate,entry,fade_start,end,intro_level]).all():raise ValueError('Invalid envelope')
    if frames<1 or rate<=0 or not 0<=entry<fade_start<end<=frames/rate or not 0<intro_level<1:
        raise ValueError('Invalid handoff timeline')
    times=np.arange(frames)/rate
    # The outgoing master is untouched until the protected line and its tail
    # have passed. Incoming is deliberately quiet underneath it.
    outgoing=1-np.clip((times-fade_start)/(end-fade_start),0,1)
    incoming=np.where(times<fade_start,
        intro_level*np.clip((times-entry)/(fade_start-entry),0,1),
        intro_level+(1-intro_level)*np.clip((times-fade_start)/(end-fade_start),0,1))
    return outgoing.astype(np.float32),incoming.astype(np.float32)


def level_summary(rows,start,end):
    values=np.asarray(rows,dtype=float)
    if values.ndim!=2 or values.shape[1]!=4 or len(values)<2 or not np.isfinite(values).all():
        raise ValueError('Invalid vocal evidence')
    if not np.allclose(np.diff(values[:,0]),.5,atol=1e-6) or np.any(values[:,1:]<0):
        raise ValueError('Missing or invalid vocal evidence bins')
    if not np.isfinite([start,end]).all() or end<=start:raise ValueError('Invalid vocal evidence interval')
    subset=[row for row in rows if row[0]<end and row[0]+.5>start]
    if not subset or start<rows[0][0] or end>rows[-1][0]+.5:
        raise ValueError('Vocal evidence does not cover the complete interval')
    values=np.asarray(subset,dtype=float)
    return {'interval_seconds':[start,end],'bins':len(subset),
            'max_vocal_rms':float(values[:,1].max()),'max_vocal_ratio':float(values[:,3].max()),
            'ratio_p95':float(np.percentile(values[:,3],95)),
            'meaning':'Model activity evidence only; no semantic phrase recognition'}


def require_quiet(rows,start,end,ratio_limit=.15):
    result=level_summary(rows,start,end)
    if result['max_vocal_ratio']>ratio_limit:raise ValueError('Vocal activity conflicts with planned handoff')
    return result


def activity_rows(vocals,master,rate,offset):
    if vocals.shape!=master.shape or vocals.ndim!=2 or vocals.shape[1]!=2 or rate<=0:
        raise ValueError('Invalid vocal screening audio')
    if not np.isfinite(vocals).all() or not np.isfinite(master).all():raise ValueError('Invalid screening samples')
    rows=[]
    hop=round(rate*.5)
    for first in range(0,len(master),hop):
        v=vocals[first:first+hop].astype(float);a=master[first:first+hop].astype(float)
        vocal_rms=float(np.sqrt(np.mean(v**2)));master_rms=float(np.sqrt(np.mean(a**2)))
        rows.append([offset+first/rate,vocal_rms,master_rms,vocal_rms/max(master_rms,1e-6)])
    return rows
