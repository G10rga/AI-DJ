"""Evaluate transition interpretation with official synthetic oracle cue labels."""
import csv
import hashlib
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from backend.app.audio.probe import probe
from backend.app.audio.reference import spectral_features,VERSION as FEATURES_VERSION
from backend.app.transition_analysis import attribute,VERSION as ANALYZER_VERSION
from scripts.setup_dj_benchmarks import digest, DATASET


def read_labels(path):
    tracks=defaultdict(dict)
    with Path(path).open(encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.strip():continue
            parts=line.rstrip('\r\n').split('\t')
            if len(parts)<4:raise ValueError('Invalid UnmixDB label row')
            start,end=float(parts[0]),float(parts[1]);index=int(parts[2]);kind=parts[3]
            if not all(math.isfinite(x) for x in (start,end)) or end<start:raise ValueError('Invalid label times')
            parameter=parts[4].strip().strip('"') if len(parts)>4 else ''
            if kind in ('start','stop'):
                if not parameter or Path(parameter).name!=parameter or '/' in parameter or '\\' in parameter:raise ValueError('Unsafe source filename')
                tracks[index]['filename']=parameter
                tracks[index][kind]=start
            elif kind=='speed':tracks[index]['speed']=float(parameter)
            elif kind in ('fadein','fadeout'):tracks[index][kind]=[start,end]
    for track in tracks.values():
        if not {'filename','start','stop','speed','fadein','fadeout'}<=track.keys():raise ValueError('Incomplete track labels')
        if not 0<track['speed']<4:raise ValueError('Invalid source speed')
    return [tracks[i] for i in sorted(tracks)]


def transition_decision(left,right):
    start=right['fadein'][0];end=left['fadeout'][1]
    if end<=start:raise ValueError('These labels do not describe a positive overlapping fade')
    decision={'mix_start':start,'mix_end':end}
    for prefix,track in (('outgoing',left),('incoming',right)):
        decision[prefix+'_source_in']=(start-track['start'])*track['speed']
        decision[prefix+'_source_out']=(end-track['start'])*track['speed']
    return decision


def evaluate(root,settings,limit=None):
    root=Path(root);manifest=json.loads((root/'sources.json').read_text(encoding='utf-8'))
    if limit is not None and limit<1:raise ValueError('Limit must be positive')
    if digest(root/'downloads'/DATASET['name'],'md5')!=DATASET['md5']:
        raise ValueError('Official dataset checksum mismatch')
    directory=Path(manifest['dataset']['directory'])/'mixotic-set222-excerpts'
    creation=Path(manifest['sources']['unmixdb-creation']['directory'])
    good_path=creation/'unmixdb-v1.1/unmixdb-v1.1-goodmixes-with-tracks-with-silence-less-than-1s.txt'
    good={Path(line.strip()).name for line in good_path.read_text().splitlines() if line.strip()}
    mixes=sorted((directory/'mixes').glob('*.mp3'))
    eligible=[p for p in mixes if p.name in good]
    if limit is not None:eligible=eligible[:limit]
    cache=root/'unmixdb-features';cache.mkdir(exist_ok=True);work=root/'tmp';work.mkdir(exist_ok=True)
    source_info={}
    def features(path):
        path=Path(path);identity=digest(path)
        if identity not in source_info:
            info=probe(path,settings);destination=cache/(identity+'-'+FEATURES_VERSION+'.npy')
            if destination.exists():array=np.load(destination,allow_pickle=False)
            else:
                array=spectral_features(path,info.duration,settings,work)
                with destination.with_suffix('.tmp').open('wb') as stream:np.save(stream,array,allow_pickle=False)
                destination.with_suffix('.tmp').replace(destination)
            source_info[identity]=(array,info.duration)
        return identity,source_info[identity][0]
    rows=[]
    for i,mix in enumerate(eligible):
        print(f'Evaluating {i+1}/{len(eligible)}: {mix.name}',flush=True)
        labels=mix.with_suffix('.labels.txt');tracks=read_labels(labels)
        mix_hash,recording=features(mix)
        for position,(left,right) in enumerate(zip(tracks,tracks[1:])):
            item={'mix':mix.name,'position':position,'expected':'gradual_blend',
                  'timing_mode':'official_oracle_labels','label_sha256':digest(labels),'recording_sha256':mix_hash,
                  'source_filenames':[left['filename'],right['filename']]}
            try:
                decision=transition_decision(left,right)
                a_hash,a=features(directory/'refsongs'/left['filename']);b_hash,b=features(directory/'refsongs'/right['filename'])
                result=attribute(recording,a,b,decision)
                item.update(decision=decision,source_hashes=[a_hash,b_hash],
                            result={key:value for key,value in result.items() if key!='curves'},
                            correct=result['technique']=='gradual_blend',recognized=result['technique']!='unknown')
            except (ValueError,OSError,RuntimeError) as exc:
                item.update(error=str(exc),correct=False,recognized=False)
            rows.append(item)
    def metrics(subset):
        total=len(subset);recognized=sum(r['recognized'] for r in subset)
        return {'examples':total,'recognized':recognized,'correct':sum(r['correct'] for r in subset),
                'unknown_or_failed':total-recognized,'coverage':recognized/total if total else None,
                'accuracy_counting_unknown_as_wrong':sum(r['correct'] for r in subset)/total if total else None,
                'conditional_accuracy':sum(r['correct'] for r in subset)/recognized if recognized else None,
                'predictions':dict(Counter(r.get('result',{}).get('technique','error') for r in subset))}
    groups={}
    for row in rows:
        parts=row['mix'].split('-');group=parts[1]+'/'+parts[2]
        groups.setdefault(group,[]).append(row)
    report={'benchmark':'unmixdb-oracle-interpretation-1','analyzer_version':ANALYZER_VERSION,
            'analyzer_implementation_sha256':digest(Path(__file__).parents[1]/'transition_analysis.py'),
            'benchmark_implementation_sha256':digest(Path(__file__)),'dataset':manifest['dataset'],
            'good_mix_list_sha256':digest(good_path),'available_audio_mixes':len(mixes),
            'eligible_good_mixes':len([p for p in mixes if p.name in good]),'evaluated_mixes':len(eligible),
            'excluded_not_in_good_subset':len([p for p in mixes if p.name not in good]),
            'label_files_without_audio':sum(not p.with_suffix('').with_suffix('.mp3').exists() for p in (directory/'mixes').glob('*.labels.txt')),
            'metrics':metrics(rows),'by_transform':{k:metrics(v) for k,v in groups.items()},'examples':rows,
            'distinct_ordered_source_pairs':len({tuple(r['source_filenames']) for r in rows}),
            'training_performed':False,'owner_annotations_modified':False,
            'limitations':['Oracle source identity and timing supplied; does not evaluate transition discovery.',
                'All annotated transitions are linear fades; this cannot validate cut/bass-swap classification.',
                'Synthetic mixes, repeated source pairs and one downloaded subset; no claim of independent human-DJ generalization.',
                'No confidence thresholds or analyzer parameters tuned on this evaluation.']}
    destination=root/'reports';destination.mkdir(exist_ok=True)
    (destination/'unmixdb-baseline.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    m=report['metrics']
    lines=['# UnmixDB recognition baseline','',f'Analyzer: `{ANALYZER_VERSION}`.',
           f'{len(eligible)} official good mixes; {m["examples"]} overlapping fades.',
           f'Distinct ordered source pairs: {report["distinct_ordered_source_pairs"]}.',
           f'Recognized: {m["recognized"]}; correct gradual blends: {m["correct"]}; unknown/failed: {m["unknown_or_failed"]}.',
           '', 'Oracle labels supply source identity and timing. This is an interpretation test, not a discovery benchmark.',
           '', '| Transform / effect | Examples | Recognized | Correct |','|---|---:|---:|---:|']
    for group,values in report['by_transform'].items():lines.append(f'| {group} | {values["examples"]} | {values["recognized"]} | {values["correct"]} |')
    lines+=['','## Limits','']+['- '+value for value in report['limitations']]
    (destination/'unmixdb-baseline.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report
