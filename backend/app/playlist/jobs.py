"""Leased playlist work with ranked retries and immutable revision-pinned results."""
import json
from .planner import joint_plan, smart_order, digest
from .evidence import cached_evidence
from .render import warp, timing, artifacts, RATE, VERSION as RENDERER
from .store import Projects
from ..config import PROJECT_ROOT
from ..improved_transitions import records_for_sources
from scripts.setup_timeline import sha256


def execute(workflow, job, owner, progress):
    payload = job['payload']; project = payload['snapshot']; settings = workflow.settings
    store = Projects(workflow); sources = project['sources']
    work = settings.data_root/'tmp'/('workflow-'+job['id']); work.mkdir(parents=True, exist_ok=True)
    def live():
        return workflow.live(job['id'], owner) and store.get(project['id'], internal=True)['revision'] == project['revision']
    def check():
        if not live(): raise ValueError('Project changed or job was cancelled; this result cannot publish')
    evidences = []
    for i, source in enumerate(sources):
        check(); progress(f'Analyzing {i+1}/{len(sources)}: {source["name"]}', .05+.30*i/len(sources))
        record = records_for_sources([source], settings, live=live)[0]
        try:
            evidences.append(cached_evidence(source, record, project['grids'].get(source['content_hash']), settings))
        except ValueError as exc:
            if len(sources) == 1 and str(exc).startswith('Beat grid needs correction'):
                t = record['effective']
                reference = {'source_hash':source['content_hash'], 'timeline_id':record['timeline_id'],
                             'revision':record['revision'], 'config':t['config']}
                evidences.append({'id':digest(reference), 'reference':reference, 'duration':t['duration_seconds'],
                                  'beats':[], 'downbeats':[], 'bpm':None, 'key':'Unknown',
                                  'waveform':t.get('features',[])})
                continue
            return {'status': 'needs_review', 'reason': f'{source["name"]}: {exc}',
                    'evidence': evidences, 'project_revision': project['revision']}
    if payload['action'] == 'reorder':
        order = smart_order(evidences)
        return {'status': 'reorder_proposal', 'order': order, 'track_ids': [sources[i]['id'] for i in order],
                'project_revision': project['revision'], 'evidence': evidences}
    excluded = {}; diagnostic = {}; attempts = []; pools = {}; plan = None; audit = None
    # Retry failed joins independently; every attempt replans the whole playlist to preserve continuity.
    maximum = max(1, 1+2*(len(sources)-1))
    for attempt in range(maximum):
        check(); progress('Ranking continuous playlist transitions', .38)
        try: candidate_plan = joint_plan(evidences, project['transitions'], excluded, pools, diagnostic)
        except ValueError as exc:
            if plan is not None:
                break
            return {'status': 'needs_review', 'reason': str(exc), 'attempts': attempts, 'evidence': evidences,
                    'plan': plan, 'project_revision': project['revision']}
        plan = candidate_plan
        estimated_bytes = int((sum(t['duration'] for t in plan['tracks']) + 4*plan['duration'])*RATE*8)
        workflow.storage.require_space(estimated_bytes, settings.min_free_bytes)
        paths = []
        for i, track in enumerate(plan['tracks']):
            check(); progress(f'Preparing continuous audio {i+1}/{len(sources)} (attempt {attempt+1})', .4+.25*i/len(sources))
            paths.append(warp(sources[i], track, settings, live))
        check(); progress('Checking original and prepared beats against tempo ramps', .7)
        audit = timing(plan, paths, sources, settings, work)
        failed = [j['join'] for j in audit['joins'] if j['status'] != 'aligned']
        with (work/'attempts.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'attempt':attempt+1, 'revision':project['revision'],
                                  'plan_id':plan['id'], 'joins':audit['joins']}, allow_nan=False)+'\n')
        for j, join in enumerate(plan['joins']):
            if not any(a['join'] == j and a['candidate_id'] == join['id'] for a in attempts):
                attempts.append({'join': j, 'candidate_id': join['id'], 'scores': join['scores'],
                                 'cost': join['cost'], 'validation': audit['joins'][j]})
        if not failed: break
        retry = False
        for index in failed:
            if index in diagnostic:
                continue
            geometry = plan['joins'][index]['geometry_id']
            tried = excluded.setdefault(index, set())
            tried.add(geometry)
            if len(tried) >= 3:
                diagnostic[index] = geometry
            else:
                retry = True
        if not retry: break
    check()
    validated = audit['status'] == 'aligned'
    exporting = validated and payload['action'] in ('auto', 'export')
    progress('Mixing and encoding full playlist' if exporting else 'Preparing editable previews', .82)
    directory = settings.data_root/'renders'/('playlist-'+job['id'])
    rendered = artifacts(plan, paths, sources, settings, work, directory, export=exporting, live=live)
    plan['geometry_id'] = plan.pop('id')
    plan['renderer_version'] = RENDERER
    plan['dsp_sha256'] = sha256(PROJECT_ROOT/'backend/app/web_assets/playlist-dsp.wasm')
    plan['validation'] = {**audit, 'encoding': rendered['encoded_timing']}
    plan['id'] = digest(plan)
    base = f'/api/v1/mix-projects/{project["id"]}/jobs/{job["id"]}/media/'
    for preview in rendered['previews']:
        for track in preview['tracks']: track['url'] = base+track['name']
    check()
    return {**rendered, 'status': ('validated' if exporting else 'preview_ready') if validated else 'needs_review',
            'reason': None if validated else 'Available ranked candidates could not resolve rhythm evidence. Correct the beat grid before exporting.',
            'plan': plan, 'attempts': attempts, 'evidence': evidences, 'project_revision': project['revision'],
            'audio_url': base+'mix.mp3' if exporting else None,
            'wav_url': base+'mix.wav' if exporting else None,
            'listening_accepted': None}
