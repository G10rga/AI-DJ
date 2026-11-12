"""Replay frozen real timing regressions into isolated storage, without owner votes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings, PROJECT_ROOT
from backend.app.storage import Storage
from backend.app.workflow import Workflow
from backend.app.vocal_rendering import render_plan
from scripts.setup_timeline import sha256


CASES = [
    ('short-context-offbeats', '7e1179e9bbfe437ba4fb5c49c03ebc1b'),
    ('early-solo-disagreement', 'd7cfda178c734a96a89d9d5ba9c1e692'),
    ('cached-grid-context', '3149351b716b4528a70aed8ba8a68a33'),
    ('reviewed-groove-preview', 'c0dd428a56464d9f8e6198253fbf65cc'),
    ('at-night-regression', 'bdf4b60c1b9546a496de81b0c2d0dd16'),
]


def write(path, data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,help='Resume an existing frozen replay without changing its implementation')
    args=parser.parse_args();settings=Settings.from_env();store=Workflow(settings)
    modules=['backend/app/audio/timing_input.py','backend/app/audio/beat_validation.py',
             'backend/app/vocal_rendering.py','scripts/transition_timing_worker.py']
    implementation={name:sha256(PROJECT_ROOT/name) for name in modules}
    if args.session:
        root=args.session.resolve(strict=True);manifest=json.loads((root/'manifest.json').read_text())
        if manifest['implementation_sha256']!=implementation:
            raise ValueError('Implementation changed; retain this replay and start a fresh session')
    else:
        root=settings.data_root/'validation'/('timing-regressions-'+uuid4().hex);root.mkdir()
        manifest={'schema':'real-timing-regressions-1','created_at':datetime.now(timezone.utc).isoformat(),
            'implementation_sha256':implementation,'cases':[],'listening_accepted':None,
            'independent_quality_claim':False,'owner_data_modified':False}
        for name,identity in CASES:
            job=store.job(identity,internal=True)
            with store.db.connection() as c:
                row=c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
            records=json.loads(row[0])['records'];plan=job['result']['plan']
            folder=root/name;folder.mkdir()
            frozen={'job_id':identity,'plan':plan,'records':records,'sources':job['payload']['sources']}
            write(folder/'request.json',frozen)
            manifest['cases'].append({'name':name,'job_id':identity,'plan_id':plan['id'],
                'request_sha256':sha256(folder/'request.json'),'prior_status':job['status']})
        write(root/'manifest.json',manifest)
    print('TIMING_REPLAYS '+str(root),flush=True)
    summaries=[]
    for case in manifest['cases']:
        folder=root/case['name'];request=folder/'request.json'
        if sha256(request)!=case['request_sha256']:
            raise ValueError('Frozen replay inputs changed')
        if (folder/'report.json').exists():
            report=json.loads((folder/'report.json').read_text())
            if report.get('output') and sha256(Path(report['output']))!=report['audio_sha256']:
                raise ValueError('Existing replay audio changed')
        else:
            frozen=json.loads(request.read_text());storage=Storage(folder/'storage');storage.initialize()
            report=render_plan(frozen['plan'],frozen['records'],[Path(s['path']) for s in frozen['sources']],settings,storage)
            write(folder/'report.json',report)
        summary={'name':case['name'],'job_id':case['job_id'],'status':report['status'],
            'identical_plan_id':report.get('plan',{}).get('id')==case['plan_id'],
            'timing_version':report.get('timing',{}).get('version'),
            'failed_checks':[{k:c.get(k) for k in ('comparison','window','kind','status','matched_fraction')}
                for j in report.get('timing',{}).get('joins',[]) for c in j.get('checks',[])
                if c['status']!='aligned' and not c.get('resolved_by')],
            'review_items':report.get('review_items',[])}
        summaries.append(summary);write(root/'summary.json',{'cases':summaries,'independent_quality_claim':False})
        print(json.dumps({k:v for k,v in summary.items() if k!='review_items'}),flush=True)
    if any(s['status']!='validated' or not s['identical_plan_id'] for s in summaries):
        raise SystemExit(1)


if __name__=='__main__':main()
