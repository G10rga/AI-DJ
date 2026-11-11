"""Prepare a source-disjoint listening batch from published owner test mixes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from backend.app.research.listening import test_mix_definition
from scripts.setup_dj_benchmarks import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('D:/AI-DJ-data/experiments/open-dj'))
    parser.add_argument('--data-root',type=Path,default=Path('D:/AI-DJ-data'))
    parser.add_argument('--test-jobs',nargs='+',required=True)
    args=parser.parse_args()
    specs=[test_mix_definition(args.data_root,identity) for identity in args.test_jobs]
    seen=set()
    for spec in specs:
        if seen.intersection(spec['source_hashes']):raise ValueError('Choose pairs with no shared source audio')
        seen.update(spec['source_hashes'])
    destination=args.root/'auditions'/('listening-batch-'+uuid4().hex)
    destination.mkdir(parents=True)
    session={'schema':'multi-pair-listening-1','created_at':datetime.now(timezone.utc).isoformat(),
             'state':'running','version_order':{'1':'existing-app','2':'djtransgan','3':'linear'},
             'pairs':specs,'source_disjoint_within_batch':True,'owner_feedback':None,'promoted':False,
             'implementation_sha256':digest(__file__)}
    path=destination/'session.json'
    path.write_text(json.dumps(session,indent=2),encoding='utf-8')
    print('LISTENING SESSION '+str(destination),flush=True)
    try:
        for index,spec in enumerate(specs):
            print(f'PAIR {index+1}/{len(specs)}: '+ ' -> '.join(spec['song_names']),flush=True)
            folder=args.root/'auditions'/spec['name']
            if (folder/'listening-reviews').exists():
                raise ValueError('Reviewed artifacts are immutable; choose a fresh session before regenerating')
            subprocess.run([sys.executable,'-m','scripts.benchmark_djtransgan','--root',str(args.root),
                            '--data-root',str(args.data_root),'--test-job',spec['job_id']],check=True)
            report_path=folder/'report.json'
            report=json.loads(report_path.read_text(encoding='utf-8'))
            if report['definition']!=spec:raise ValueError('Published source plan changed during batch')
            for output in report['outputs'].values():
                if digest(output['path'])!=output['sha256']:raise ValueError('Batch output changed')
                if output['longest_near_silent_run_seconds']>=.5:
                    raise ValueError('Unexpected dropout in audition; batch not accepted')
            spec['benchmark_report_sha256']=digest(report_path)
            spec['outputs']=report['outputs']
            path.write_text(json.dumps(session,indent=2),encoding='utf-8')
    except Exception as exc:
        session.update(state='failed',error=str(exc))
        path.write_text(json.dumps(session,indent=2),encoding='utf-8')
        raise
    session['state']='ready_for_listening'
    path.write_text(json.dumps(session,indent=2),encoding='utf-8')
    lines=['# Three-pair listening test','','All previews: 60 seconds, mono, matched loudness. Handoff at 30 seconds.',
           'Listen around 20–40 seconds. Choose any winners, all bad, or no clear preference for each pair.',
           'No votes are recorded automatically.','','| Pair | 1 Existing | 2 AI | 3 Simple crossfade |',
           '|---|---|---|---|']
    for index,spec in enumerate(specs):
        title=' → '.join(spec['song_names'])
        links=[f'[{number}](../{spec["name"]}/{version}.mp3)' for number,version in session['version_order'].items()]
        lines.append(f'| {index+1}. {title} | '+' | '.join(links)+' |')
    lines+=['','The existing app also differs in source separation and gain processing. This comparison does not isolate one individual effect.',
            'Sources/cues/output hashes and technical checks are in session.json and each pair report. Musical acceptance is pending.']
    (destination/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('READY '+str(destination),flush=True)


if __name__=='__main__':main()
