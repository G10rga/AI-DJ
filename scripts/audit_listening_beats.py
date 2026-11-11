"""Run the pinned independent beat/downbeat model on rejected prepared sources."""
import argparse
import importlib.metadata
import json
from pathlib import Path

import soundfile as sf
import torch
from beat_this.inference import Audio2Beats

from backend.app.research.beat_alignment import marker_alignment,bar_support,require_alignment,VERSION
from scripts.setup_dj_benchmarks import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',type=Path)
    parser.add_argument('--models',type=Path,default=Path('D:/AI-DJ-data/timeline/models'))
    args=parser.parse_args()
    checkpoint=args.models/'final0.ckpt'
    expected='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
    if digest(checkpoint)!=expected:raise ValueError('Pinned beat checkpoint changed')
    torch.set_num_threads(4)
    tracker=Audio2Beats(checkpoint_path=str(checkpoint),device='cpu',dbn=False)
    session=json.loads(args.session.read_text(encoding='utf-8'))
    root=args.session.parent.parent
    audit={'model':'Beat This final0','gate_version':VERSION,'checkpoint_sha256':expected,'session_sha256':digest(args.session),
           'packages':{name:importlib.metadata.version(name) for name in ('torch','beat-this','numpy','soxr','soundfile')},
           'implementation_sha256':digest(__file__),'pairs':[],
           'limits':'Independent predictions, not human truth. Downbeat agreement does not establish phrase or vocal compatibility.'}
    output=args.session.parent/'timing-audit/independent-beats.json'
    output.parent.mkdir(exist_ok=True)
    for spec in session['pairs']:
        print('Auditing '+ ' -> '.join(spec['song_names']),flush=True)
        work=root/spec['name'];report=json.loads((work/'report.json').read_text(encoding='utf-8'))
        row={'song_names':spec['song_names'],'sources':[]}
        for index in range(2):
            path=work/f'source-{index}.wav'
            samples,rate=sf.read(path,dtype='float32')
            with torch.inference_mode():beats,downs=tracker(samples,rate)
            row['sources'].append({'prepared_sha256':digest(path),'beats':list(map(float,beats)),
                                   'downbeats':list(map(float,downs))})
        start,end=report['cue_region_seconds']
        for field,tolerance in [('beats',.025),('downbeats',.07)]:
            row[field]=marker_alignment(row['sources'][0][field],row['sources'][1][field],start+1,end-1,tolerance)
        row['bar_support']=[bar_support(source['beats'],source['downbeats'],start+1,end-1) for source in row['sources']]
        try:require_alignment(row)
        except ValueError:row['publication_allowed']=False
        else:row['publication_allowed']=True
        audit['pairs'].append(row)
        output.write_text(json.dumps(audit,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({key:row[key] for key in ('beats','downbeats','bar_support','publication_allowed')}),flush=True)
    print('Audit saved: '+str(output),flush=True)


if __name__=='__main__':main()
