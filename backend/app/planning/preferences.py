"""Explicit owner feedback -> pairwise preference ranking, stored locally."""
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

VERSION='context-preference-ranker-2'
FEATURES=['tempo_gap_octaves','overlap_seconds','overlap_bars','a_start_fraction','b_start_fraction',
          'outgoing_vocal_fade_seconds','incoming_vocal_fade_seconds','mid_swap_seconds','bass_swap_seconds',
          'vocal_eq','stem_separation','long_profile']
CONTEXT_FIELDS=['energy_change_db','harmonic_distance','embedding_distance',
                'uncontrolled_vocal_collision','outgoing_trend_db','midrange_rise_db']
FEATURES += [name+suffix for name in CONTEXT_FIELDS for suffix in ('','_known')]


def stored_features(row):
    vector=json.loads(row['features_json'])
    if len(vector)==12:vector += [0.]*(len(FEATURES)-12)
    if len(vector)!=len(FEATURES):raise ValueError('Unsupported preference features')
    return np.asarray(vector,dtype=float)


def features(report):
    tracks=report['tracks']; recipe=report.get('recipe',{});schedule=recipe.get('vocal_schedule',{})
    a,b=tracks
    vector=[abs(math.log2(a['source_bpm']/b['source_bpm'])),report['overlap_seconds'],
            report['overlap_seconds']*report['target_bpm']/240,
            a['source_in']/max(a.get('source_duration',a['source_out']),1),
            b['source_in']/max(b.get('source_duration',b['source_out']),1),
            schedule.get('outgoing_fade_duration_seconds',0),schedule.get('incoming_fade_duration_seconds',0),
            recipe.get('mid_swap_duration_seconds',0),recipe.get('bass_swap_duration_seconds',0),
            bool(schedule.get('vocal_eq')),bool(report.get('stems')),recipe.get('blend_profile')=='long_groove']
    evidence=report.get('requested_candidate',{}).get('evidence',{})
    for name in CONTEXT_FIELDS:
        value=evidence.get(name)
        vector += [float(value) if value is not None else 0.,float(value is not None)]
    if len(tracks)!=2 or not all(math.isfinite(float(x)) for x in vector):raise ValueError('Invalid pair features')
    return list(map(float,vector))


class PreferenceStore:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'preferences.sqlite3'
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,pair_key TEXT NOT NULL,report_json TEXT NOT NULL,features_json TEXT NOT NULL,audio_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,a TEXT NOT NULL REFERENCES candidates(id),b TEXT REFERENCES candidates(id),value REAL,notes TEXT,created_at TEXT NOT NULL);''')
            c.execute('CREATE TABLE IF NOT EXISTS audition_reviews(comparison_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,choice TEXT NOT NULL,notes TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:yield c
        finally:c.close()
    def register(self,path):
        r=json.loads(Path(path).read_text(encoding='utf-8'));vector=features(r)
        audio=Path(r['output']).resolve(strict=True)
        h=hashlib.sha256()
        with audio.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        pair=hashlib.sha256(':'.join(t['content_hash'] for t in r['tracks']).encode()).hexdigest()
        identity=hashlib.sha256((h.hexdigest()+pair).encode()).hexdigest()[:16]
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)',(identity,pair,json.dumps(r),json.dumps(vector),h.hexdigest()))
        return identity
    def candidates(self):
        with self.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM candidates ORDER BY id')]
    def feedback(self,kind,a,b=None,value=None,notes=''):
        rows={x['id']:x for x in self.candidates()}
        if a not in rows or (b is not None and b not in rows):raise ValueError('Unknown candidate')
        if kind in ('prefer','tie','neither'):
            if b not in rows:raise ValueError('A preference needs a second registered candidate')
            if a==b or rows[a]['pair_key']!=rows[b]['pair_key']:raise ValueError('Compare distinct versions of the same ordered songs')
        elif kind=='rate':
            if value is None or not math.isfinite(value) or not 1<=value<=5:raise ValueError('Ratings must be 1–5')
        else:raise ValueError('Unknown feedback kind')
        with self.connect() as c:
            c.execute('INSERT INTO feedback(kind,a,b,value,notes,created_at) VALUES(?,?,?,?,?,?)',
                      (kind,a,b,value,notes,datetime.now(timezone.utc).isoformat()))
        return self.train()
    def comparisons(self):
        rows={x['id']:x for x in self.candidates()};votes={};ratings={}
        with self.connect() as c:events=list(c.execute('SELECT * FROM feedback ORDER BY id'))
        for event in events:
            if event['kind'] in ('prefer','tie','neither'):
                votes[tuple(sorted((event['a'],event['b'])))]=(event['a'],event['b']) if event['kind']=='prefer' else None
            else:ratings[event['a']]=event['value']
        ids=sorted(ratings)
        for i,a in enumerate(ids):
            for b in ids[i+1:]:
                if rows[a]['pair_key']==rows[b]['pair_key'] and ratings[a]!=ratings[b]:
                    votes.setdefault((a,b),(a,b) if ratings[a]>ratings[b] else (b,a))
        data=[]
        for vote in votes.values():
            if vote is None:continue
            a,b=vote
            difference=stored_features(rows[a])-stored_features(rows[b])
            if np.linalg.norm(difference)>1e-10:data.append((difference,rows[a]['pair_key'],a,b))
        return data

    def review(self,comparison_id,a,b,choice,expected_revision,notes=''):
        if choice not in ('a','b','tie','neither') or type(expected_revision) is not int:
            raise ValueError('Choose A, B, tie or neither and supply the saved revision')
        if not isinstance(notes,str) or len(notes)>1000:raise ValueError('Keep the reason under 1000 characters')
        rows={r['id']:r for r in self.candidates()}
        if a==b or a not in rows or b not in rows or rows[a]['pair_key']!=rows[b]['pair_key']:
            raise ValueError('Compare distinct versions of the same ordered songs')
        winner,loser=(b,a) if choice=='b' else (a,b)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT revision FROM audition_reviews WHERE comparison_id=?',(comparison_id,)).fetchone()
            revision=previous[0] if previous else 0
            if revision!=expected_revision:raise ValueError('Feedback changed in another window; reload before saving')
            c.execute('INSERT INTO feedback(kind,a,b,value,notes,created_at) VALUES(?,?,?,?,?,?)',
                ('prefer' if choice in ('a','b') else choice,winner,loser,None,notes,datetime.now(timezone.utc).isoformat()))
            c.execute('INSERT OR REPLACE INTO audition_reviews VALUES (?,?,?,?)',(comparison_id,revision+1,choice,notes))
        return {'review':self.review_state(comparison_id),'model':self.train()}

    def review_state(self,comparison_id):
        with self.connect() as c:
            row=c.execute('SELECT revision,choice,notes FROM audition_reviews WHERE comparison_id=?',(comparison_id,)).fetchone()
        return dict(row) if row else {'revision':0,'choice':None,'notes':''}
    @staticmethod
    def fit(data):
        x=np.array([d[0] for d in data]);x=np.concatenate((x,-x));y=np.array([1]*len(data)+[0]*len(data))
        scaler=StandardScaler(with_mean=False).fit(x)
        model=LogisticRegression(fit_intercept=False,C=.25,solver='lbfgs',random_state=11).fit(scaler.transform(x),y)
        return scaler,model
    def train(self):
        data=self.comparisons();groups=sorted({x[1] for x in data})
        result={'version':VERSION,'features':FEATURES,'comparisons':len(data),'song_pairs':len(groups),
                'ready':len(data)>=6 and len(groups)>=3,'minimum_comparisons':6,'minimum_song_pairs':3,
                'note':'Relative preferences, not calibrated quality. More feedback is needed for reliable generalization.'}
        if data:
            scaler,model=self.fit(data);result.update(scale=scaler.scale_.tolist(),weights=model.coef_[0].tolist())
            correct=total=0
            for group in groups:
                train=[d for d in data if d[1]!=group];test=[d for d in data if d[1]==group]
                if not train:continue
                sc,mo=self.fit(train)
                scores=mo.decision_function(sc.transform(np.array([d[0] for d in test])))
                correct+=sum(float(s)>0 for s in scores);total+=len(scores)
            result['held_out_song_pair_accuracy']=correct/total if total else None
            result['validation_comparisons']=total
            result['training_pairs']=[[d[2],d[3]] for d in data]
        temporary=self.root/('ranker-'+uuid4().hex+'.tmp');temporary.write_text(json.dumps(result,indent=2),encoding='utf-8');temporary.replace(self.root/'ranker.json')
        return result
    def rank(self,pair_key=None):
        model=self.train();rows=[r for r in self.candidates() if pair_key is None or r['pair_key']==pair_key]
        if pair_key is None and len({r['pair_key'] for r in rows})>1:raise ValueError('Specify one song pair; scores are only comparable within a pair')
        if not model.get('weights'):return {'model':model,'ranking':[]}
        results=[]
        for row in rows:
            score=float(np.dot(stored_features(row)/model['scale'],model['weights']))
            results.append({'id':row['id'],'pair_key':row['pair_key'],'score':score,'output':json.loads(row['report_json'])['output']})
        return {'model':model,'experimental':not model['ready'],'ranking':sorted(results,key=lambda x:(-x['score'],x['id']))}

    def settings(self,report,fade_bars=4,profile='standard'):
        from copy import deepcopy
        model=self.train()
        if not model['ready']:return {'ready':False,'fade_bars':fade_bars,'profile':profile,'reason':'Insufficient explicit feedback'}
        choices=[(fade_bars,profile)]+[(b,p) for b in (2,4,8) for p in ('standard','long_groove') if (b,p)!=(fade_bars,profile)]
        scored=[]
        for bars,mode in choices:
            if mode=='long_groove' and report['overlap_seconds']<30:continue
            trial=deepcopy(report);recipe=trial.setdefault('recipe',{});schedule=recipe.setdefault('vocal_schedule',{})
            duration=bars*240/trial['target_bpm']
            available=[t.get('output_seconds',(t['source_out']-t['source_in'])*t['source_bpm']/trial['target_bpm']) for t in trial['tracks']]
            if duration>min(available)/2:continue
            schedule.update(outgoing_fade_duration_seconds=duration,incoming_fade_duration_seconds=duration,vocal_eq=True)
            beat=60/trial['target_bpm'];recipe.update(blend_profile=mode,mid_swap_duration_seconds=min((64 if mode=='long_groove' else 8)*beat,trial['overlap_seconds']/2),bass_swap_duration_seconds=(4 if mode=='long_groove' else .5)*beat)
            trial['stems']=True
            score=float(np.dot(np.array(features(trial))/model['scale'],model['weights']))
            scored.append((score,bars,mode))
        if not scored:return {'ready':False,'fade_bars':fade_bars,'profile':profile,'reason':'No supported candidate settings fit these excerpts'}
        winner=max(scored,key=lambda x:x[0])
        return {'ready':True,'fade_bars':winner[1],'profile':winner[2],'relative_score':winner[0],
                'comparisons':model['comparisons'],'held_out_song_pair_accuracy':model['held_out_song_pair_accuracy']}
