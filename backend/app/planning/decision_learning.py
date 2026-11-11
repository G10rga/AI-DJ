"""Supervised source cues/overlap and masked style labels from reviewed decisions."""
import json
import hashlib
import math
from pathlib import Path
from importlib.metadata import version
import numpy as np
from backend.app.timelines import canonical
from scripts.setup_timeline import sha256

VERSION = 'reviewed-cue-model-1'
STYLES = ('groove_32', 'controlled_16', 'eq_8', 'cut')
TARGETS = ('outgoing_entry_fraction', 'outgoing_exit_fraction', 'incoming_entry_fraction',
           'incoming_exit_fraction', 'log_overlap')


def source_features(features, duration):
    values = np.asarray(features, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 32 or not np.isfinite(values).all() or duration <= 0:
        raise ValueError('Invalid source context features')
    centered = values-values.mean(axis=1, keepdims=True)
    return np.concatenate((centered.mean(axis=0), centered.std(axis=0), [math.log1p(duration)/10])).tolist()


def dataset_from_snapshot(snapshot, references, progress=None):
    sources, rows = {}, []
    for i, example in enumerate(snapshot['examples']):
        if progress:
            progress(i, len(snapshot['examples']))
        decision = example['decision']
        if decision.get('reviewed') is not True or decision.get('learn') is not True:
            raise ValueError('Training snapshot contains an unapproved example')
        pair = example['sources']
        for source in pair:
            digest = source['content_hash']
            if digest not in sources:
                sources[digest] = source_features(references._features(source), source['duration_seconds'])
        a, b = [s['duration_seconds'] for s in pair]
        overlap = decision['mix_end']-decision['mix_start']
        if not 0 <= overlap <= 128:
            raise ValueError('Reviewed overlap exceeds the supported 128-second range')
        target = [decision['outgoing_source_in']/a, decision['outgoing_source_out']/a,
                  decision['incoming_source_in']/b, decision['incoming_source_out']/b,
                  math.log1p(overlap)/math.log(129)]
        if not all(math.isfinite(v) and 0 <= v <= 1.000001 for v in target):
            raise ValueError('Reviewed source cues are outside their original audio')
        style = decision.get('recipe')
        origin = 'human' if style in STYLES else 'unknown'
        estimate = example.get('automatic_style')
        if style is None and estimate:
            if (estimate.get('confidence') != 'high' or estimate.get('human_confirmed') is not False
                    or estimate.get('label_origin') != 'automatic_spectral_estimate'
                    or estimate.get('review_revision') != example['review_revision']
                    or estimate.get('decision_hash') != hashlib.sha256(canonical(decision).encode()).hexdigest()
                    or estimate.get('recording_hash') != snapshot['recording_hash']
                    or estimate.get('source_hashes') != [s['content_hash'] for s in pair]):
                raise ValueError('Automatic style provenance does not match this reviewed example')
            style = estimate.get('recipe')
            if style in STYLES:
                origin = 'automatic_spectral_estimate'
        rows.append({'position': example['position'], 'review_revision': example['review_revision'],
                     'source_hashes': [s['content_hash'] for s in pair], 'durations': [a,b],
                     'x': sources[pair[0]['content_hash']]+sources[pair[1]['content_hash']],
                     'y': target, 'style': STYLES.index(style) if style in STYLES else -1,
                     'style_origin': origin, 'style_weight': .35 if origin == 'automatic_spectral_estimate' else 1.})
    if len(rows) < 2:
        raise ValueError('Include at least two completed listening reviews before training')
    if any(r['style_origin']=='automatic_spectral_estimate' for r in rows):
        recording=references.get(snapshot['reference_id'])['import']['recording']
        if sha256(Path(recording['path']))!=snapshot['recording_hash']:
            raise ValueError('Reference recording changed since automatic style analysis')
    return {'version': VERSION, 'snapshot': snapshot, 'rows': rows,
            'feature_config': {'version': 'global-centered-spectrum-1', 'bands': 32,
                               'per_source': 'mean/std and log duration', 'dimensions': 130},
            'targets': TARGETS, 'styles': STYLES}


def source_split(rows):
    tail = rows[-max(1, math.ceil(len(rows)*.25)):]
    held = {h for row in tail for h in row['source_hashes']}
    train, evaluation, excluded = [], [], []
    for i, row in enumerate(rows):
        flags = [h in held for h in row['source_hashes']]
        (evaluation if all(flags) else train if not any(flags) else excluded).append(i)
    if len(train) < 2 or not evaluation:
        return {'train': list(range(len(rows))), 'evaluation': [], 'excluded': [],
                'reason': 'Not enough source-disjoint pairs for evaluation; training only',
                'independent_reference_sets': False}
    return {'train': train, 'evaluation': evaluation, 'excluded': excluded,
            'reason': 'Tail source identities held out; cross-boundary and repeated-source leakage excluded',
            'independent_reference_sets': False}


def network():
    import torch
    class CueNetwork(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.body = torch.nn.Sequential(torch.nn.Linear(130,24), torch.nn.SiLU(), torch.nn.Dropout(.15))
            self.cues = torch.nn.Linear(24,5)
            self.style = torch.nn.Linear(24,len(STYLES))
        def forward(self, x):
            context = self.body(x)
            return self.cues(context).sigmoid(), self.style(context)
    return CueNetwork()


def fit(dataset, destination, *, epochs=300, seed=11):
    import torch
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    rows = dataset['rows']
    split = source_split(rows)
    train = split['train']
    x, y = np.array([r['x'] for r in rows], dtype=np.float32), np.array([r['y'] for r in rows], dtype=np.float32)
    if x.shape != (len(rows),130) or y.shape != (len(rows),5) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Invalid training dimensions or non-finite descriptors')
    mean, scale = x[train].mean(axis=0), np.maximum(x[train].std(axis=0), .1)
    tx, ty = torch.tensor((x-mean)/scale), torch.tensor(y)
    labels = torch.tensor([r['style'] for r in rows])
    known = [i for i in train if rows[i]['style'] >= 0]
    model = network()
    target_mean = np.clip(y[train].mean(axis=0), .0001, .9999)
    with torch.no_grad():
        model.cues.weight.zero_()
        model.cues.bias.copy_(torch.tensor(np.log(target_mean/(1-target_mean))))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.1)
    trace = []
    for epoch in range(epochs):
        model.train(); optimizer.zero_grad()
        cues, styles = model(tx)
        loss = torch.nn.functional.mse_loss(cues[train],ty[train])
        if known:
            weights=torch.tensor([rows[i].get('style_weight',1.) for i in known])
            loss = loss+.05*(torch.nn.functional.cross_entropy(styles[known],labels[known],reduction='none')*weights).mean()
        if not torch.isfinite(loss):
            raise ValueError('Training produced non-finite loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.); optimizer.step()
        if epoch == 0 or epoch+1 == epochs or (epoch+1)%50 == 0:
            trace.append({'epoch':epoch+1,'training_loss':float(loss.detach())})
    model.eval()
    with torch.no_grad():
        cues, logits = model(tx); predicted=cues.numpy(); style_prediction=logits.argmax(dim=1).numpy()
    supported = sorted({rows[i]['style'] for i in known})
    def metrics(indices):
        if not indices:
            return None
        truth=y[indices]; actual=predicted[indices]
        durations=np.array([[rows[i]['durations'][0]]*2+[rows[i]['durations'][1]]*2 for i in indices])
        labeled=[i for i in indices if rows[i]['style'] in supported and rows[i].get('style_origin','human')=='human']
        automatic=[i for i in indices if rows[i]['style'] in supported and rows[i].get('style_origin')=='automatic_spectral_estimate']
        return {'examples':len(indices), 'cue_mae_seconds':float(np.mean(abs(actual[:,:4]-truth[:,:4])*durations)),
                'overlap_mae_seconds':float(np.mean(abs(np.expm1(actual[:,4]*math.log(129))-np.expm1(truth[:,4]*math.log(129))))),
                'normalized_mse':float(np.mean((actual-truth)**2)),
                'mean_baseline_mse':float(np.mean((target_mean-truth)**2)),
                'style_accuracy':float(np.mean([style_prediction[i]==rows[i]['style'] for i in labeled])) if labeled else None,
                'evaluated_style_examples':len(labeled),
                'automatic_style_agreement':float(np.mean([style_prediction[i]==rows[i]['style'] for i in automatic])) if automatic else None,
                'automatic_style_examples':len(automatic)}
    report={'version':VERSION,'status':'experimental','active':False,'examples':len(rows),
            'style_examples':sum(r['style']>=0 for r in rows),'trained_style_examples':len(known),
            'human_style_examples':sum(r['style']>=0 and r.get('style_origin','human')=='human' for r in rows),
            'automatic_style_examples':sum(r['style']>=0 and r.get('style_origin')=='automatic_spectral_estimate' for r in rows),
            'train':metrics(train),'evaluation':metrics(split['evaluation']), 'split':split,
            'trace':trace,'listening_approval':False,
            'limitations':['Single reference set; no independent reference-set test.',
                           'Small-sample cue/style imitation does not establish musical improvement.',
                           'Unlabeled styles are masked. Excluded and pending reviews are not training examples.',
                           'Automatic spectral labels have weight 0.35; agreement with them is not human style accuracy.']}
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    torch.save(model.state_dict(),destination/'checkpoint.pt')
    config={'version':VERSION,'mean':mean.tolist(),'scale':scale.tolist(),'supported_styles':supported,
            'epochs':epochs,'seed':seed,'runtime':{p:version(p) for p in ('torch','numpy')},
            'implementation_hash':sha256(Path(__file__))}
    for name, value in (('config.json',config),('dataset.json',dataset),('report.json',report)):
        (destination/name).write_text(canonical(value),encoding='utf-8')
    manifest={'version':VERSION,'report':report,'files':{name:sha256(destination/name) for name in
              ('checkpoint.pt','config.json','dataset.json','report.json')}}
    (destination/'manifest.json').write_text(canonical(manifest),encoding='utf-8')
    return manifest


def load(destination):
    import torch
    destination=Path(destination)
    manifest=json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=VERSION or set(manifest['files'])!={'checkpoint.pt','config.json','dataset.json','report.json'}:
        raise ValueError('Unsupported decision model')
    for name,digest in manifest['files'].items():
        if sha256(destination/name)!=digest:
            raise ValueError('Decision model artifact changed: '+name)
    config=json.loads((destination/'config.json').read_text(encoding='utf-8'))
    if config['version']!=VERSION or len(config['mean'])!=130 or len(config['scale'])!=130:
        raise ValueError('Unsupported model features')
    model=network();model.load_state_dict(torch.load(destination/'checkpoint.pt',map_location='cpu',weights_only=True),strict=True);model.eval()
    return model,config,manifest


def predict(destination, pairs):
    import torch
    model,config,_=load(destination)
    x=np.array([p['x'] for p in pairs],dtype=np.float32)
    if x.ndim!=2 or x.shape[1]!=130 or not np.isfinite(x).all():
        raise ValueError('Invalid test song context')
    with torch.no_grad():
        cues,styles=model(torch.tensor((x-config['mean'])/np.array(config['scale']),dtype=torch.float32))
    result=[]
    for pair,cue,logits in zip(pairs,cues.numpy(),styles.numpy()):
        a,b=pair['durations']
        supported=config['supported_styles']
        style=STYLES[max(supported,key=lambda i:float(logits[i]))] if supported else None
        result.append({'outgoing_source_in':float(cue[0]*a),'outgoing_source_out':float(cue[1]*a),
                       'incoming_source_in':float(cue[2]*b),'incoming_source_out':float(cue[3]*b),
                       'overlap_seconds':float(np.expm1(cue[4]*math.log(129))),'recipe':style})
    return result
