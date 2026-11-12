"""Serve an isolated review QA database; never write browser test reviews to owner data."""
import json
import os
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings
from backend.app.timelines import TimelineStore
from backend.app.transition_review import capture
from backend.app.workflow import Workflow


def main():
    import uvicorn
    from backend.app.web import create_app
    original=Settings.from_env(); catalog=Workflow(original).catalog(internal=True)
    selected=[next(row for row in catalog if row['id']==identity) for identity in
              ('7fd2f1a8dd844b8f962466dc','f351665b5858e9bfeeaaf827')]
    root=original.data_root/'validation'/('review-browser-'+uuid4().hex);root.mkdir(parents=True)
    # Junctions share only the existing pinned dependency/model runtimes. The
    # database, review rows, jobs, scratch files and resulting audio are isolated.
    if os.name!='nt':
        for name in ('timeline','separation'): (root/name).symlink_to(original.data_root/name,target_is_directory=True)
    else:
        import subprocess
        for name in ('timeline','separation'):
            subprocess.run(['powershell','-NoProfile','-Command',
                f"New-Item -ItemType Junction -Path '{root/name}' -Target '{original.data_root/name}' | Out-Null"],check=True)
    settings=Settings(data_root=root,ffmpeg=original.ffmpeg,ffprobe=original.ffprobe,min_free_bytes=0,port=8009)
    store=Workflow(settings); timeline=TimelineStore(root); records=[]
    for source in selected:
        record=TimelineStore(original.data_root).for_content(source['content_hash'],profile='transition-foundation-1')
        keys=timeline.save(source['path'],record['prediction'],record['prediction']['config'])
        records.append(timeline.get(**keys))
    queued=store.enqueue('test_mix',{'pipeline':'improved-transitions-1','sources':selected,'seconds':72.,'baseline':True,
                                  'foundation_records':records})
    owner='isolated-fixture-seed';job=store.claim(owner);capture(store,job,owner,records)
    store.finish(job['id'],owner,'succeeded',{'status':'needs_review','review_items':[{
        'code':'isolated_browser_fixture','message':'Isolated browser workflow check. Listen, mark both originals, then preview; independent timing checks still apply.'}]})
    # Previously validated real comparison audio, copied into this isolated
    # catalog, permits UI/feedback QA without manufacturing owner labels.
    import shutil
    prior=json.loads((original.data_root/'analysis/improved-validation-493301e77ce44d309d4fa3e79e0f3400.json').read_text())
    store.enqueue('pair_audition',{'pipeline':'improved-transitions-1','sources':selected,'baseline':True})
    comparison=store.claim(owner);capture(store,comparison,owner,records)
    for index,report in enumerate(prior['alternatives']):
        target=store.storage.root/'renders'/f'qa-comparison-{index}.mp3';shutil.copyfile(report['output'],target);report['output']=str(target)
    store.finish(comparison['id'],owner,'succeeded',prior)
    (root/'fixture.json').write_text(json.dumps({'root':str(root),'job_id':job['id'],'url':f'http://127.0.0.1:8009/transition-review/{job["id"]}'}),encoding='utf-8')
    print('ISOLATED_FIXTURE '+str(root/'fixture.json'),flush=True)
    uvicorn.run(create_app(settings),host='127.0.0.1',port=8009)


if __name__=='__main__':main()
