"""Completed mixes, version-pinned streams and audition playback through HTTP."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Excerpt, MixPlan, Transition
from backend.app.playback import PlaybackLibrary
from backend.app.storage import Storage
from backend.app.web import create_app


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.storage=Storage(self.root);self.storage.initialize()
        self.db=Database(self.root/'app.sqlite3');self.db.initialize()
        self.plan=MixPlan('mix',1,(Excerpt('a',0,120,180,120,120),Excerpt('b',0,120,180,120,120)),(Transition('controlled',32,16),))
        entries=[{'entry_id':n,'path':str(self.root/(n+'.mp3')),'analysis':{'content_hash':n}} for n in ('a','b')]
        self.db.register_plan(entries,self.plan)
        self.audio=self.storage.path('renders','set.mp3');self.audio.write_bytes(b'first rendered audio')
        self.report={'duration':208,'applied_plan':json.loads(self.plan.to_json()),
                     'tracks':[{'name':'First song.mp3','start_seconds':0,'duration':120},
                               {'name':'Second song.mp3','start_seconds':88,'duration':120}]}
        attempt=self.db.begin_render(self.plan,{})
        self.db.finish_render(attempt,self.audio.name,self.report)
        self.client=TestClient(create_app(Settings(data_root=self.root)),base_url='http://127.0.0.1')

    def test_mix_catalog_play_seek_download_and_tracklist(self):
        self.assertIn('Your mixed sets',self.client.get('/').text)
        self.assertIn('Source track playback',self.client.get('/timelines').text)
        mix=self.client.get('/api/v1/mixes').json()['mixes'][0]
        self.assertEqual(mix['title'],'First song → Second song')
        self.assertEqual(mix['duration_seconds'],208)
        self.assertEqual(mix['tracks'][1]['start_seconds'],88)
        self.assertEqual(mix['transitions'][0]['handoff_seconds'],104)
        response=self.client.get(mix['audio_url'],headers={'Range':'bytes=0-4'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'first')
        self.assertIn('inline',response.headers['content-disposition'])
        response=self.client.get(mix['download_url'])
        self.assertIn('attachment',response.headers['content-disposition'])
        self.assertEqual(response.content,self.audio.read_bytes())

    def test_playback_stays_pinned_after_new_revision_and_failed_rerender(self):
        first_url=self.client.get('/api/v1/mixes').json()['mixes'][0]['audio_url']
        second=replace(self.plan,revision=2);self.db.save_plan(second)
        attempt=self.db.begin_render(second,{})
        self.db.fail_render(attempt,'render failed')
        mix=self.client.get('/api/v1/mixes').json()['mixes'][0]
        self.assertTrue(mix['previous_version_kept']);self.assertTrue(mix['latest_render_failed'])
        self.assertEqual(self.client.get(first_url).content,b'first rendered audio')
        attempt=self.db.begin_render(second,{})
        self.storage.path('renders','second.mp3').write_bytes(b'new audio')
        self.db.finish_render(attempt,'second.mp3',self.report)
        self.assertEqual(self.client.get('/api/v1/mixes/mix/audio').content,b'new audio')
        self.assertEqual(self.client.get(first_url).content,b'first rendered audio')
        self.assertEqual(self.client.get('/api/v1/mixes/mix/audio?revision=99').status_code,404)

    def test_missing_and_unregistered_media_not_exposed(self):
        self.assertEqual(self.client.get('/api/v1/mixes/unknown/audio').status_code,404)
        self.audio.unlink()
        mix=self.client.get('/api/v1/mixes').json()['mixes'][0]
        self.assertFalse(mix['available'])
        self.assertEqual(self.client.get(mix['audio_url']).status_code,404)

    def test_only_registered_matched_auditions_are_playable(self):
        preview=self.storage.path('renders','preview.mp3');preview.write_bytes(b'preview audio')
        with self.db.connection() as c:
            c.execute('INSERT INTO transition_candidates(id,pair_key,snapshot_json) VALUES (?,?,?)',
                      ('candidate','pair',json.dumps({'recipe':'controlled_16'})))
            payload={'output':str(preview),'duration':128,'handoff_seconds':64,'loudness':{'integrated_lufs':-20},
                     'tracks':[{'path':'one.mp3'},{'path':'two.mp3'}]}
            c.execute("INSERT INTO candidate_events(candidate_id,kind,payload_json) VALUES ('candidate','audition',?)",(json.dumps(payload),))
            first=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute("INSERT INTO candidate_events(candidate_id,kind,payload_json) VALUES ('candidate','audition',?)",(json.dumps(payload),))
            latest=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        rows=self.client.get('/api/v1/auditions').json()['auditions']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],str(latest))
        self.assertEqual(rows[0]['title'],'16-bar controlled blend')
        self.assertEqual(self.client.get(rows[0]['audio_url'],headers={'Range':'bytes=0-6'}).content,b'preview')
        self.assertEqual(self.client.get(f'/api/v1/auditions/{first}/audio').content,b'preview audio')
        payload['output']=str(self.root/'preview.mp3')
        with self.db.connection() as c:
            c.execute("INSERT INTO candidate_events(candidate_id,kind,payload_json) VALUES ('candidate','audition',?)",(json.dumps(payload),))
            unsafe=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.assertEqual(self.client.get('/api/v1/auditions').json()['auditions'],[])
        self.assertEqual(self.client.get(f'/api/v1/auditions/{unsafe}/audio').status_code,404)


if __name__=='__main__':unittest.main()
