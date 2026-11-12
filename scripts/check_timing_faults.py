"""Prove the real independent worker rejects deliberately corrupted timing."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import numpy as np
import soundfile as sf

from backend.app.config import Settings, PROJECT_ROOT
from scripts.setup_timeline import sha256


def write(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path,help='Captured request with retained prepared/encoded PCM')
    args=parser.parse_args();capture=args.capture.resolve(strict=True)
    baseline=json.loads((capture/'request.json').read_text())
    root=capture/('deliberate-faults-'+uuid4().hex);root.mkdir()
    runtime=Settings.from_env().data_root/('timeline/venv/Scripts/python.exe' if os.name=='nt' else 'timeline/venv/bin/python')
    beat=60/baseline['plan']['sources'][0]['target_bpm']
    policy=sha256(PROJECT_ROOT/'backend/app/audio/timing_input.py')
    cases=[('half-beat-shift',beat/2),('one-beat-bar-phase',beat),('tempo-drift',.02),('encoded-time-shift',beat/2)]
    write(root/'manifest.json',{'schema':'real-timing-faults-1','baseline_request_sha256':sha256(capture/'request.json'),
        'detector_policy_sha256':policy,'cases':cases,'published_audio':False,'owner_data_modified':False})
    summaries=[]
    for name,amount in cases:
        folder=root/name;folder.mkdir();request=deepcopy(baseline)
        field='encoded_pcm' if name=='encoded-time-shift' else 'prepared_paths'
        source=request[field] if field=='encoded_pcm' else request[field][1]
        samples,rate=sf.read(source,dtype='float32',always_2d=True)
        if name=='tempo-drift':
            positions=np.arange(len(samples));warped=positions*1.02
            altered=np.column_stack([np.interp(warped,positions,samples[:,i],right=0.) for i in range(2)])
        else:
            count=round(amount*rate);altered=np.zeros_like(samples);altered[count:]=samples[:-count]
        target=folder/'deliberately-corrupted.wav';sf.write(target,altered,rate,subtype='FLOAT')
        if field=='encoded_pcm':
            request['encoded_pcm']=str(target);request['encoded_pcm_sha256']=sha256(target)
        else:
            request['prepared_paths'][1]=str(target);request['prepared_sha256'][1]=sha256(target)
        request['detector_policy_sha256']=policy
        write(folder/'request.json',request)
        subprocess.run([str(runtime),'-m','scripts.transition_timing_worker',str(folder/'request.json'),str(folder/'report.json')],
                       cwd=PROJECT_ROOT,check=True,timeout=600)
        report=json.loads((folder/'report.json').read_text())
        failed=[c for join in report['joins'] for c in join['checks'] if c['status']!='aligned' and not c.get('resolved_by')]
        expected='encoded_overlap' if field=='encoded_pcm' else 'prepared_pair'
        rejected=report['status']=='needs_review' and any(c['comparison'].startswith(expected) for c in failed)
        summary={'name':name,'status':report['status'],'correctly_rejected':rejected,
                 'failed_checks':len(failed),'expected_failure_stage':expected}
        summaries.append(summary);write(root/'summary.json',{'cases':summaries})
        print(json.dumps(summary),flush=True)
        if not rejected:raise RuntimeError('Deliberately corrupted timing was not rejected')
    print('TIMING_FAULTS_PASSED '+str(root),flush=True)


if __name__=='__main__':main()
