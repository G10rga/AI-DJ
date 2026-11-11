"""Compare saved and alignment-derived source mappings without changing reviews."""
import json
import numpy as np
from copy import deepcopy
from backend.app.config import Settings
from backend.app.workflow import Workflow
from backend.app.transition_analysis import attribute
import backend.app.transition_analysis as analyzer


def main():
    original_fit=analyzer.fit_gains
    fits=[]
    def measured(*args):
        result=original_fit(*args)
        fits.append(float(np.median(result[1])))
        return result
    analyzer.fit_gains=measured
    store=Workflow(Settings.from_env())
    ref=next(r for r in store.reviews.list() if r['draft_id'])
    batch=store.reviews.batch(ref['draft_id'])
    imported=store.reviews.references.get(batch['reference_id'])['import']
    recording=store.reviews.references._features(imported['recording'])
    for row in batch['transitions']:
        d=row['review']
        if not d or not d.get('reviewed') or not d.get('learn') or not 2<d['mix_end']-d['mix_start']<128:continue
        position=row['position']
        sources=[next(s for s in imported['tracks'][position+i]['sources'] if s['content_hash']==d[k])
                 for i,k in enumerate(('outgoing_hash','incoming_hash'))]
        features=[store.reviews.references._features(s) for s in sources]
        candidates={'saved':d}
        unit=deepcopy(d)
        for prefix in ('outgoing','incoming'):
            unit[prefix+'_source_out']=unit[prefix+'_source_in']+d['mix_end']-d['mix_start']
        candidates['unit_rate_from_entry']=unit
        mapped=deepcopy(d)
        for i,prefix in enumerate(('outgoing','incoming')):
            track=batch['tracks'][position+i]
            mapping=track.get('mapping')
            if mapping and track['source_hash']==d[prefix+'_hash']:
                mapped[prefix+'_source_in']=(d['mix_start']-mapping['offset_seconds'])/mapping['scale']
                mapped[prefix+'_source_out']=(d['mix_end']-mapping['offset_seconds'])/mapping['scale']
        candidates['matched_mapping']=mapped
        result={}
        for name,decision in candidates.items():
            try:
                fits.clear()
                analysis=attribute(recording,*features,decision)
                curves=analysis.get('curves',[])
                trend={}
                if len(curves)>4:
                    for band in ('bass','mids','upper'):
                        values=np.array([r[band] for r in curves])
                        trend[band]={'early':values[:max(2,len(values)//5)].mean(axis=0).tolist(),
                                     'late':values[-max(2,len(values)//5):].mean(axis=0).tolist()}
                result[name]={'technique':analysis['technique'],'confidence':analysis['confidence'],**analysis['quality'],'trend':trend,'band_errors':fits[-3:]}
            except ValueError as exc:result[name]={'error':str(exc)}
        print(json.dumps({'position':position,'results':result}),flush=True)


if __name__=='__main__':main()
