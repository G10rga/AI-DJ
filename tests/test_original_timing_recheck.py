"""Context rechecks retain failures and never excuse actual audio disagreement."""
from copy import deepcopy
import unittest
import numpy as np

from backend.app.audio.beat_validation import audit_join, recheck_original_grid


class OriginalTimingRecheckTests(unittest.TestCase):
    def fixture(self):
        beats=np.arange(0,30,.48).tolist()
        observed={'beats':beats,'downbeats':beats[::4]}
        def shifted(amount):
            return {kind:[t-(amount if t>=12 else 0) for t in values] for kind,values in observed.items()}
        cached=shifted(.03);local=shifted(.015)
        expected=[cached,observed];pair=[observed,deepcopy(observed)]
        audit=audit_join(*pair,expected,4.,20.,observed)
        audit['solo_checks']=[{'status':'aligned'},{'status':'aligned'}]
        return audit,pair,expected,{0:{'raw':local,'prepared_gain':deepcopy(local)}}

    def resolve(self, audit, pair, expected, originals):
        return recheck_original_grid(audit,pair,expected,originals,4.,20.)

    def test_context_jitter_requires_both_variants_and_preserves_failed_measurements(self):
        args=self.fixture();original=deepcopy(args[0])
        self.assertEqual(original['status'],'needs_review')
        result=self.resolve(*args)
        self.assertEqual(result['status'],'validated')
        self.assertEqual(args[0],original)
        failures=[c for c in result['checks'] if c['status']!='aligned']
        self.assertTrue(failures)
        self.assertTrue(all(c['resolved_by']=='same-context-original-1' for c in failures))
        checks=result['original_context_recheck']['checks']
        self.assertEqual({c['variant'] for c in checks},{'raw','prepared_gain'})
        self.assertEqual({c['window'] for c in checks},{'whole','early','late'})
        self.assertTrue(all(c['tolerance_seconds']==(.025 if c['kind']=='beats' else .07) for c in checks))

    def test_actual_prepared_or_encoded_failure_unknown_or_solo_failure_stays_blocked(self):
        for comparison,status in [('prepared_pair','mismatch'),('encoded_overlap_0','mismatch'),
                                  ('original_mapping_0','unknown')]:
            args=self.fixture()
            failed=next(c for c in args[0]['checks'] if c['status']!='aligned')
            failed.update(comparison=comparison,status=status)
            self.assertEqual(self.resolve(*args)['status'],'needs_review')
        args=self.fixture();args[0]['solo_checks'][0]['status']='unknown'
        self.assertEqual(self.resolve(*args)['status'],'needs_review')
        args=self.fixture();args[0]['solo_checks']=[]
        self.assertEqual(self.resolve(*args)['status'],'needs_review')

    def test_missing_variant_or_local_phase_error_stays_blocked(self):
        args=self.fixture();del args[3][0]['prepared_gain']
        self.assertEqual(self.resolve(*args)['status'],'needs_review')
        args=self.fixture()
        args[3][0]['prepared_gain']['downbeats']=[t+.48 for t in args[3][0]['prepared_gain']['downbeats']]
        self.assertEqual(self.resolve(*args)['status'],'needs_review')

    def test_cached_markers_must_all_be_accounted_for(self):
        args=self.fixture();args[2][0]['beats']=sorted([*args[2][0]['beats'],13.2])
        result=self.resolve(*args)
        self.assertEqual(result['status'],'needs_review')
        cached=[c for c in result['original_context_recheck']['checks'] if c['comparison']=='cached_to_local_original']
        self.assertTrue(any(c.get('matched_fraction',1)<1 for c in cached))

    def test_actual_local_beat_slip_stays_blocked(self):
        args=self.fixture()
        args[3][0]['raw']['beats']=[t-(.08 if t>12 else 0) for t in args[1][0]['beats']]
        result=self.resolve(*args)
        self.assertEqual(result['status'],'needs_review')


if __name__=='__main__':unittest.main()
