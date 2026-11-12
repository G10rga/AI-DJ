"""Encoding checks must distinguish gain/codec noise from a real time shift."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import soundfile as sf
from backend.app.audio.encoding_timing import verify_encoding
class EncodingTimingTests(unittest.TestCase):
 def test_gain_noise_and_time_shift(self):
  rng=np.random.default_rng(42);samples=rng.normal(0,.08,(44100*4,2)).astype('float32')
  with tempfile.TemporaryDirectory() as folder:
   a=Path(folder)/'raw.wav';b=Path(folder)/'encoded.wav';sf.write(a,samples,44100,subtype='FLOAT')
   sf.write(b,samples*.3+rng.normal(0,.0001,samples.shape),44100,subtype='FLOAT')
   self.assertEqual(verify_encoding(a,b,.2,3.8)['status'],'aligned')
   for count in [88,11025]:
    shifted=np.zeros_like(samples);shifted[count:]=samples[:-count]*.3;sf.write(b,shifted,44100,subtype='FLOAT')
    self.assertEqual(verify_encoding(a,b,.2,3.8)['status'],'mismatch')
if __name__=='__main__':unittest.main()
