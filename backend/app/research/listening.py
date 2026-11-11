"""Freeze existing published two-track test mixes for external listening tests."""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from scripts.setup_dj_benchmarks import digest


def aligned_sources(cues, originals, center, overlap, duration, track_starts, delays):
    if len(cues)!=2 or len(originals)!=2 or len(track_starts)!=2 or len(delays)!=2:
        raise ValueError('A listening comparison requires exactly two tracks')
    numbers=[center,overlap,duration,*track_starts,*delays]
    if not all(math.isfinite(x) for x in numbers) or not 0<overlap<60:
        raise ValueError('Invalid listening window')
    if center<30 or center+30>duration:
        raise ValueError('Insufficient 30-second context around the handoff')
    if any(abs(delay)>1e-7 for delay in delays):
        raise ValueError('PCM-delayed renders are unsupported; do not silently shift their cues')
    sources=[]
    for i,(cue,original) in enumerate(zip(cues,originals)):
        ratio=cue['target_bpm']/cue['source_bpm']
        length=(cue['source_out']-cue['source_in'])/ratio
        expected=0. if i==0 else center-overlap/2
        if abs(track_starts[i]-expected)>.02 or (i==0 and abs(length-(center+overlap/2))>.02):
            raise ValueError('Applied cues do not match published track positions')
        if i==1 and length<30+overlap/2-.02:
            raise ValueError('Incoming source has insufficient context')
        if digest(original['path'])!=original['content_hash']:
            raise ValueError('Original song changed')
        start=cue['source_in']+((center-30)*ratio if i==0 else 0)
        sources.append({'path':original['path'],'start':start,'ratio':ratio})
    return sources


def test_mix_definition(data_root,job_id):
    if not re.fullmatch('[0-9a-f]{32}',job_id):raise ValueError('Invalid test job ID')
    root=Path(data_root).resolve()
    with sqlite3.connect(f'file:{root.as_posix()}/app.sqlite3?mode=ro',uri=True) as db:
        row=db.execute('SELECT status,payload_json,result_json FROM workflow_jobs WHERE id=? AND kind=?',
                       (job_id,'test_mix')).fetchone()
        if not row or row[0]!='succeeded':raise ValueError('Choose a successfully published two-song test mix')
        payload,result=json.loads(row[1]),json.loads(row[2])
        published=db.execute('SELECT storage_name,metadata_json FROM renders WHERE mix_id=? AND revision=?',
                             (result['mix_id'],result['revision'])).fetchone()
    if not published:raise ValueError('Published render is missing')
    name,metadata=published
    baseline=(root/'renders'/name).resolve()
    if Path(name).name!=name or not baseline.is_relative_to(root/'renders'):
        raise ValueError('Published render escaped storage')
    report=json.loads(metadata)
    cues=report['applied_plan']['excerpts']
    if len(report['joins'])!=1 or len(report['tracks'])!=2:
        raise ValueError('Choose a two-song published mix')
    overlap=report['joins'][0]['overlap']
    starts=[track['start_seconds'] for track in report['tracks']]
    center=starts[1]+overlap/2
    sources=aligned_sources(cues,payload['sources'],center,overlap,report['duration'],starts,report['pcm_delays_seconds'])
    return {'name':'test-pair-'+job_id,'job_id':job_id,'job_kind':'test_mix',
            'song_names':[source['name'] for source in payload['sources']],
            'source_hashes':[source['content_hash'] for source in payload['sources']],
            'mix_id':result['mix_id'],'revision':result['revision'],'applied_plan':report['applied_plan'],
            'sources':sources,'overlap':overlap,'handoff_in_original_seconds':center,
            'baseline':str(baseline),'baseline_sha256':digest(baseline),
            'baseline_report_sha256':hashlib.sha256(metadata.encode()).hexdigest(),
            'baseline_hash_origin':'Observed published file, pinned at benchmark preparation',
            'preparation':'Frozen published applied cues, tempo and overlap; mono downmix; same prepared inputs for GAN/linear; existing app retains stem processing'}
