"""Find observed regular bar spans and fit tempo without quantized-median bias."""
import numpy as np


def stable_spans(source,anchor,bars=8,minimum_start=35,after_span_context=25):
    beats=np.asarray(source['beats'],dtype=float)
    downs=np.asarray(source['downbeats'],dtype=float)
    if not np.isfinite(beats).all() or not np.isfinite(downs).all() or np.any(np.diff(beats)<=0) or np.any(np.diff(downs)<=0):
        raise ValueError('Invalid source marker sequence')
    candidates=[]
    for i in range(len(downs)-bars):
        selected=downs[i:i+bars+1]
        if selected[0]<minimum_start or selected[-1]+after_span_context>source['duration_seconds']:continue
        counts=[int(np.sum((beats>=left-.05)&(beats<right-.05))) for left,right in zip(selected,selected[1:])]
        if counts!=[4]*bars:continue
        first=int(np.argmin(abs(beats-selected[0])))
        observed=beats[first:first+bars*4+1]
        if len(observed)!=bars*4+1 or abs(observed[-1]-selected[-1])>.04:continue
        period,origin=np.polyfit(np.arange(len(observed)),observed,1)
        residual=abs(observed-(origin+np.arange(len(observed))*period))
        if not .4<period<.6 or np.percentile(residual,90)>.015:continue
        if abs(origin-anchor)>20:continue
        candidates.append({'bar_index':i,'source_cue':float(origin),'source_bpm':float(60/period),
                           'period_seconds':float(period),'fit_p90_seconds':float(np.percentile(residual,90)),
                           'observed_beats':observed.tolist(),'observed_downbeats':selected.tolist(),
                           'distance_from_old_cue_seconds':float(abs(origin-anchor)),'bars':bars})
    return sorted(candidates,key=lambda item:(item['distance_from_old_cue_seconds'],item['source_cue']))
