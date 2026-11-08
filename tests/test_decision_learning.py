import importlib.util,json
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock
import numpy as np
from backend.app.planning.decision_learning import source_features,source_split,dataset_from_snapshot,fit,predict,load
from backend.app.planning.decision_plan import supported_cue,trial_plan


def dataset(styles=False):
    rng=np.random.default_rng(6);rows=[]
    for i in range(16):
        x=rng.normal(size=130)
        rows.append({'position':i,'review_revision':1,'source_hashes':[str(i),str(i+1)],'durations':[180,200],
            'x':x.tolist(),'y':[float(.5+.1*np.tanh(x[0])),.75,.2,.3,.5],
            'style':2 if styles and i%2==0 else -1})
    return {'rows':rows,'snapshot':{'reviewed':True}}


class DecisionDataTests(unittest.TestCase):
    def test_frozen_summary_gain_invariance_and_disjoint_sources(self):
        values=np.random.default_rng(4).normal(size=(200,32))
        self.assertTrue(np.allclose(source_features(values,180),source_features(values+8,180)))
        rows=dataset()['rows'];split=source_split(rows)
        train={h for i in split['train'] for h in rows[i]['source_hashes']}
        held={h for i in split['evaluation'] for h in rows[i]['source_hashes']}
        self.assertFalse(train&held)
        self.assertEqual(source_split(rows[:2])['evaluation'],[])

    def test_snapshot_only_allows_completed_included_observations(self):
        references=Mock();references._features.return_value=np.ones((100,32))
        decision={'reviewed':False,'learn':True}
        with self.assertRaisesRegex(ValueError,'unapproved'):
            dataset_from_snapshot({'examples':[{'decision':decision}]},references)
        references._features.assert_not_called()

    def test_model_cues_search_nearby_supported_regions_without_changing_recipe(self):
        analysis={'audio':{'duration':200},'energy':[.2]*200,'energy_frame_seconds':1,
                  'rhythm':{'bpm':120,'reliable':True,'windows':[
                      {'start':0,'end':80,'phase':0,'bpm':120}, {'start':112,'end':192,'phase':0,'bpm':120}]}}
        self.assertEqual(supported_cue(analysis,93,16),112)
        with self.assertRaisesRegex(ValueError,'no stable nearby'):
            supported_cue(analysis,100,64,maximum_shift=4)
        entries=[{'entry_id':str(i),'path':str(i)+'.mp3','analysis':analysis} for i in range(2)]
        prediction={'outgoing_source_in':93,'outgoing_source_out':109,'incoming_source_in':40,
                    'incoming_source_out':56,'overlap_seconds':16,'recipe':None}
        plan,details=trial_plan(entries,'test',72,[prediction],'model')
        self.assertEqual(plan.transitions[0].bars,8)
        self.assertEqual({e.track_id for e in plan.excerpts},{'0','1'})
        self.assertEqual(details['joins'][0]['prediction']['outgoing_source_in'],93)
        self.assertTrue(details['joins'][0]['notes'])
        self.assertTrue(details['strict_join_settings'])


@unittest.skipUnless(importlib.util.find_spec('torch'),'Use isolated PyTorch runtime')
class DecisionTrainingTests(unittest.TestCase):
    def test_real_training_unknown_style_mask_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=fit(dataset(),root/'first',epochs=20)
            second=fit(dataset(),root/'second',epochs=20)
            self.assertEqual(first['report']['train'],second['report']['train'])
            self.assertEqual(first['report']['trained_style_examples'],0)
            self.assertFalse(first['report']['active'])
            prediction=predict(root/'first',[{'x':[0.]*130,'durations':[180,200]}])[0]
            self.assertIsNone(prediction['recipe'])
            self.assertTrue(all(np.isfinite(v) for k,v in prediction.items() if k!='recipe'))
            (root/'first'/'config.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'artifact changed'):load(root/'first')

    def test_only_known_training_styles_are_predicted(self):
        with tempfile.TemporaryDirectory() as directory:
            model=fit(dataset(True),directory,epochs=10)
            self.assertGreater(model['report']['trained_style_examples'],0)
            self.assertEqual(predict(directory,[{'x':[0.]*130,'durations':[180,200]}])[0]['recipe'],'eq_8')


if __name__=='__main__':unittest.main()
