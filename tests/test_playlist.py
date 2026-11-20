"""Playlist geometry, independent timing and revision fencing."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.playlist.planner import corrected_grid, joint_plan, trajectory
from backend.app.playlist.validation import compare_markers
from backend.app.playlist.store import Projects
from backend.app.web import create_app
from backend.app.workflow import Workflow
from scripts.setup_timeline import sha256


def evidence(index, tempo=120, seconds=23, prominence=.7):
    beats = np.arange(.15, seconds, 60/tempo).tolist()
    return {'id':str(index), 'duration':seconds, 'beats':beats, 'downbeats':beats[::4],
            'bpm':tempo, 'vocals':[{'start':0, 'end':seconds, 'prominence':prominence}],
            'features':[], 'sections':[]}


class PlaylistTests(unittest.TestCase):
    def test_five_and_thirty_song_geometry(self):
        for count in (5, 30):
            plan = joint_plan([evidence(i, 109+i%15*2) for i in range(count)])
            self.assertEqual(len(plan['tracks']), count)
            self.assertEqual(len(plan['joins']), count-1)
            self.assertEqual(plan['tracks'][0]['source_in'], 0)
            self.assertEqual(plan['tracks'][-1]['source_out'], 23)
            for index in range(1, count-1):
                middle = plan['tracks'][index]
                a, b = plan['joins'][index-1]['b_end'], plan['joins'][index]['a_cue']
                anchors = np.array(middle['map'])
                self.assertGreater(b, a)
                local = np.interp([a,b], *anchors.T)
                self.assertAlmostEqual(local[1]-local[0], b-a)

    def test_ramp_evaluates_against_variable_map_and_flags_rhythm_errors(self):
        outgoing = np.r_[0., np.cumsum(np.linspace(.48,.52,24))]
        incoming = np.r_[0., np.cumsum(np.linspace(.59,.62,24))]
        clock = trajectory(outgoing, incoming)
        self.assertLess(np.diff(clock)[0], np.diff(clock)[-1])
        self.assertEqual(compare_markers(clock, clock+.01)['status'], 'aligned')
        self.assertEqual(compare_markers(clock, clock+.14)['status'], 'mismatch')
        self.assertEqual(compare_markers(clock, clock[::2])['status'], 'mismatch')
        self.assertEqual(compare_markers(clock, [])['status'], 'uncertain')
        self.assertEqual(compare_markers(clock[::4], clock[1::4])['status'], 'mismatch')
        self.assertEqual(compare_markers(clock[:9:4], clock[4:9:4])['status'], 'aligned')
        bars = np.arange(0, 12, 2)
        observed = np.arange(0, 11)
        self.assertEqual(compare_markers(bars, observed, downbeats=True)['status'], 'uncertain')
        self.assertEqual(compare_markers(bars, observed, downbeats=True, human_phase=True)['status'], 'aligned')

    def test_corrected_local_anchor_and_vocal_end(self):
        t = {'beats':{'times':[]}, 'downbeats':{'times':[]}, 'duration_seconds':30}
        beats, downs = corrected_grid(t, {'bpm':120,'first_downbeat':.1,'bar_phase':1,'anchors':[[0,.1],[20,10.4]]})
        self.assertAlmostEqual(beats[20],10.4)
        self.assertAlmostEqual(downs[0],beats[1])
        plan = joint_plan([evidence(0,seconds=40),evidence(1,seconds=40)],
                          {'0':{'bars':4,'vocal_ending':33}})
        join = plan['joins'][0]
        self.assertGreater(join['a_end'],35)
        hold = np.interp(33,join['a_beats'],join['output_beats'])/join['duration']
        self.assertAlmostEqual(np.interp(hold,*np.array(join['automation']['a']['gain']).T),1)

    def test_short_tracks_cannot_invent_bars_and_large_changes_warn(self):
        with self.assertRaisesRegex(ValueError, 'needs grid/cue correction'):
            joint_plan([evidence(0, seconds=3),evidence(1, seconds=3)])
        a, b = evidence(0, tempo=94, seconds=40), evidence(1, tempo=150, seconds=40)
        plan = joint_plan([a,b], {'0':{'bars':2}})
        self.assertTrue(plan['joins'][0]['warnings'])
        self.assertGreater(plan['joins'][0]['scores']['vocal_collision'], 0)

    def test_api_and_stale_or_cancelled_job_cannot_publish(self):
        with tempfile.TemporaryDirectory() as root:
            settings = Settings(data_root=Path(root), min_free_bytes=0)
            workflow = Workflow(settings)
            path = Path(root)/'a.wav'
            path.write_bytes(b'audio fixture')
            with workflow.db.connection() as c:
                c.execute('INSERT INTO tracks(id,content_hash,original_name,storage_name,metadata_json) VALUES (?,?,?,?,?)',
                          ('a',sha256(path),'a.wav','external:a',json.dumps({'external_path':str(path)})))
            client = TestClient(create_app(settings), base_url='http://localhost')
            base = '/api/v1/mix-projects'
            track = client.get(base).json()['library'][0]['id']
            project = client.post(base,json={'track_ids':[track,track]}).json()
            url = base+'/'+project['id']
            original = client.get(url+'/source/0?revision=1', headers={'Range':'bytes=0-4'})
            self.assertEqual(original.status_code,206)
            self.assertEqual(original.content,b'audio')
            stale = client.post(url+'/auto',json={'expected_revision':1}).json()
            self.assertEqual(workflow.claim('test')['id'],stale['id'])
            self.assertEqual(client.patch(url,json={'expected_revision':1,'name':'Revised'}).status_code,200)
            self.assertEqual(client.post(url+'/export',json={'expected_revision':1}).status_code,409)
            workflow.finish(stale['id'],'test','succeeded',{'status':'validated','audio_url':'fake'})
            self.assertEqual(workflow.job(stale['id'])['status'],'interrupted')
            latest = client.post(url+'/auto',json={'expected_revision':2}).json()
            self.assertEqual(workflow.claim('test')['id'],latest['id'])
            client.post(url+'/cancel',json={'expected_revision':2,'job_id':latest['id']})
            workflow.finish(latest['id'],'test','succeeded',{'status':'validated','audio_url':'fake'})
            self.assertEqual(workflow.job(latest['id'])['status'],'cancelled')
            self.assertIsNone(Projects(workflow).get(project['id'])['playable'])
