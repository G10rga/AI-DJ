"""Audit prepared audition timing; preserve rejected audio and owner feedback."""
import argparse
import json
from pathlib import Path
import subprocess

from backend.app.audio.phase import pulse_grid, compare_grids
from backend.app.config import Settings
from scripts.setup_dj_benchmarks import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',type=Path)
    args=parser.parse_args()
    session=json.loads(args.session.read_text(encoding='utf-8'))
    root=args.session.parent.parent
    settings=Settings.from_env()
    destination=args.session.parent/'timing-audit'
    destination.mkdir(exist_ok=True)
    audit={'session_sha256':digest(args.session),'implementation_sha256':digest(__file__),'pairs':[],
           'limits':'Low-frequency pulse fits are heuristic; they do not prove beat/downbeat or phrase correctness.'}
    for index,spec in enumerate(session['pairs']):
        work=root/spec['name']
        report=json.loads((work/'report.json').read_text(encoding='utf-8'))
        cue=report['cue_region_seconds']
        period=60/spec['applied_plan']['excerpts'][0]['target_bpm']
        paths=[]
        for i in range(2):
            path=destination/f'{index}-{i}.wav'
            subprocess.run([settings.ffmpeg,'-v','error','-nostdin','-y','-i',str(work/f'source-{i}.wav'),
                            '-c:a','pcm_s16le',str(path)],check=True,capture_output=True,timeout=60)
            paths.append(path)
        row={'songs':spec['song_names'],'period_seconds':period,'windows':[]}
        for offset,span in [(0.,cue[1]-cue[0]),(0.,6.),(cue[1]-cue[0]-6.,6.)]:
            item={'offset_seconds':offset,'span_seconds':span,'grids':[]}
            for path in paths:
                try:item['grids'].append(pulse_grid(path,cue[0]+offset,span,period))
                except ValueError as exc:item['grids'].append({'error':str(exc)})
            if all('error' not in grid for grid in item['grids']):
                item['comparison']=compare_grids(*item['grids'],span)
            row['windows'].append(item)
        audit['pairs'].append(row)
        print(json.dumps(row,indent=2),flush=True)
    (destination/'report.json').write_text(json.dumps(audit,indent=2,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main()
