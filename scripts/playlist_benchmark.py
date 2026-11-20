"""Render a level-matched simple crossfade from a saved two-song audition."""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.app.config import Settings
from backend.app.playlist.planner import automation
from backend.app.playlist.render import RATE, apply_dsp, loudness, normalize
from backend.app.playlist.store import Projects
from backend.app.workflow import Workflow


def compare(project_id, job_id, target, settings):
    workflow = Workflow(settings)
    store = Projects(workflow)
    job = workflow.job(job_id, internal=True)
    result = job['result'] or {}
    previews = result.get('previews', [])
    if len(previews) != 1 or result['plan']['validation']['status'] != 'aligned':
        raise ValueError('Choose an independently validated two-song project job')
    preview = previews[0]
    target.mkdir(parents=True, exist_ok=False)
    rendered = {}
    for label in ('auto', 'crossfade'):
        layers = []
        for track, side in zip(preview['tracks'], ('a', 'b')):
            audio = store.media(project_id, job_id, track['name'])
            curves = track['segments']
            if label == 'crossfade':
                curves = [{'start': preview['overlap_start'], 'end': preview['overlap_end'],
                           'curves': automation('blend')[side]}]
            staged = target/f'{label}-{side}.wav'
            apply_dsp(audio, staged, curves, target, settings)
            signal, _ = sf.read(staged, dtype='float32', always_2d=True)
            layers.append(signal)
            staged.unlink()
        raw = target/'raw.wav'
        sf.write(raw, np.add(*layers), RATE, subtype='FLOAT')
        output = target/(label+'.wav')
        normalize(raw, output, settings)
        rendered[label] = {'file': output.name, 'metrics': loudness(output, settings)}
        raw.unlink()
    for scratch in ('input.f32', 'output.f32', 'automation.json'):
        (target/scratch).unlink(missing_ok=True)
    gap = abs(float(rendered['auto']['metrics']['input_i'])-float(rendered['crossfade']['metrics']['input_i']))
    report = {'project_id':project_id, 'job_id':job_id, 'plan_id':result['plan']['id'],
              'level_difference_lu':gap, 'matched_within_0_3_lu':gap<=.3, 'artifacts':rendered,
              'owner_judgments':None}
    (target/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_id')
    parser.add_argument('job_id')
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.project_id, args.job_id, args.target, Settings.from_env()), indent=2))
