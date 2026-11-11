"""Analyze full original tracks for the single corrected-crossfade experiment."""
import json
from pathlib import Path
import subprocess
import importlib.metadata
import numpy as np
import torch
from beat_this.inference import Audio2Beats
from scripts.setup_dj_benchmarks import digest


def main():
    root=Path('D:/AI-DJ-data/experiments/open-dj')
    old=root/'auditions/test-pair-6fe842b8e47940d3a67914b7740a46d6/report.json'
    spec=json.loads(old.read_text(encoding='utf-8'))['definition']
    work=root/'alignment/at-night-stupidisco-1';work.mkdir(parents=True,exist_ok=True)
    checkpoint=Path('D:/AI-DJ-data/timeline/models/final0.ckpt')
    expected='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
    if digest(checkpoint)!=expected:raise ValueError('Beat checkpoint changed')
    torch.set_num_threads(4)
    tracker=Audio2Beats(checkpoint_path=str(checkpoint),device='cpu',dbn=False)
    report={'checkpoint_sha256':expected,'source_report_sha256':digest(old),
            'packages':{n:importlib.metadata.version(n) for n in ('torch','beat-this','numpy','soxr')},'sources':[]}
    for source,expected_hash in zip(spec['sources'],spec['source_hashes']):
        path=Path(source['path'])
        if digest(path)!=expected_hash:raise ValueError('Original changed')
        print('Full-context beat analysis: '+path.name,flush=True)
        raw=subprocess.check_output(['D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe',
                '-v','error','-nostdin','-i',str(path),'-ac','1','-ar','24000','-f','f32le','-'],timeout=120)
        samples=np.frombuffer(raw,dtype='<f4').copy()
        with torch.inference_mode():beats,downs=tracker(samples,24000)
        item={'path':str(path),'sha256':expected_hash,'duration_seconds':len(samples)/24000,
              'beats':list(map(float,beats)),'downbeats':list(map(float,downs))}
        report['sources'].append(item)
        (work/'full-beats.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(f'{len(beats)} beats, {len(downs)} downbeats',flush=True)
    print('Saved '+str(work/'full-beats.json'),flush=True)


if __name__=='__main__':main()
