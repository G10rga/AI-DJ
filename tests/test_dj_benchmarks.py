"""Ground-truth coordinate mapping and fail-closed research artifact handling."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from backend.app.research.unmixdb import read_labels, transition_decision
from backend.app.research.djtransgan import verify_checkpoint
from backend.app.research.listening import aligned_sources
from scripts.setup_dj_benchmarks import digest
from scripts.setup_dj_benchmarks import extract, ensure_extracted


class BenchmarkTruthTests(unittest.TestCase):
    def test_published_source_coordinates_preserve_tempo_and_track_placement(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'a.mp3';source.write_bytes(b'audio identity only')
            originals=[{'path':str(source),'content_hash':digest(source)}]*2
            # Outgoing ends at 70s, incoming starts at 50s, handoff 60s.
            cues=[{'source_in':10.,'source_out':87.,'source_bpm':100.,'target_bpm':110.},
                  {'source_in':20.,'source_out':74.,'source_bpm':100.,'target_bpm':90.}]
            result=aligned_sources(cues,originals,60.,20.,110.,[0.,50.],[0.,0.])
            self.assertAlmostEqual(result[0]['start'],43.)
            self.assertAlmostEqual(result[0]['ratio'],1.1)
            self.assertAlmostEqual(result[1]['start'],20.)
            self.assertAlmostEqual(result[1]['ratio'],.9)
            for starts,delays,center in [([0.,51.],[0.,0.],60.),([0.,50.],[0.,.05],60.),([0.,50.],[0.,0.],20.)]:
                with self.assertRaises(ValueError):
                    aligned_sources(cues,originals,center,20.,110.,starts,delays)
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Original song changed'):
                aligned_sources(cues,originals,60.,20.,110.,[0.,50.],[0.,0.])

    def test_source_mapping_uses_virtual_start_and_playback_speed(self):
        # Virtual start can precede the recording; speed is source seconds per
        # recording second, not its inverse. Splice cutpoints are not DJ cuts.
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mix.labels.txt'
            path.write_text('0\t0\t0\tstart\tleft.mp3\n'
                            '40\t40\t0\tstop\tleft.mp3\n'
                            '0\t0\t0\tspeed\t1.25\n'
                            '0\t4\t0\tfadein\n'
                            '20\t28\t0\tfadeout\n'
                            '4\t4\t0\tcutpoint\n'
                            '-4\t-4\t1\tstart\tright.mp3\n'
                            '60\t60\t1\tstop\tright.mp3\n'
                            '0\t0\t1\tspeed\t0.8\n'
                            '20\t28\t1\tfadein\n'
                            '50\t58\t1\tfadeout\n',encoding='utf-8')
            decision=transition_decision(*read_labels(path))
            self.assertEqual(decision['mix_start'],20)
            self.assertEqual(decision['mix_end'],28)
            self.assertEqual(decision['outgoing_source_in'],25)
            self.assertEqual(decision['outgoing_source_out'],35)
            self.assertAlmostEqual(decision['incoming_source_in'],19.2)
            self.assertAlmostEqual(decision['incoming_source_out'],25.6)

    def test_incomplete_or_unsafe_labels_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'labels.txt'
            for text in ['0\t0\t0\tstart\ta.mp3\n','0\t0\t0\tstart\t../a.mp3\n']:
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):read_labels(path)

    def test_missing_or_tampered_model_fails_before_torch_import(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(FileNotFoundError):verify_checkpoint(root)
            (root/'checkpoints').mkdir()
            (root/'checkpoints/djtransgan_minmax.pt').write_bytes(b'not trained weights')
            with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):verify_checkpoint(root)

    def test_archive_rejects_windows_paths_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for member in ['../outside','..\\outside','C:/outside','/absolute']:
                with zipfile.ZipFile(root/'bad.zip','w') as archive:archive.writestr(member,b'bad')
                with self.assertRaises(ValueError):extract(root/'bad.zip',root/'output')
            link=zipfile.ZipInfo('link');link.external_attr=0o120777<<16
            with zipfile.ZipFile(root/'bad.zip','w') as archive:archive.writestr(link,'../outside')
            with self.assertRaises(ValueError):extract(root/'bad.zip',root/'output')

    def test_partial_extraction_is_repaired_and_completed_stamp_is_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'output';output.mkdir()
            (output/'source.py').write_text('partial')
            with zipfile.ZipFile(root/'good.zip','w') as archive:
                archive.writestr('source.py','complete')
            ensure_extracted(root/'good.zip',output)
            self.assertEqual((output/'source.py').read_text(),'complete')
            self.assertTrue((output/'.archive-sha256').exists())


if __name__=='__main__':unittest.main()
