import unittest
import numpy as np
from backend.app.audio.beat_validation import clock_alignment
class ClockTests(unittest.TestCase):
 def test_quantization(self):
  a=np.arange(0,30,.473);b=a+.023
  a=np.round(a/.02)*.02;b=np.round(b/.02)*.02
  c=clock_alignment(a,b,1,29);self.assertEqual(c['status'],'aligned');self.assertEqual(c['raw_marker_check']['status'],'mismatch')
 def test_real_faults(self):
  a=np.arange(0,30,.48)
  for b in [a+.03,a*1.002,a+.24,np.delete(a,np.arange(20,35)),np.sort(np.r_[a,a[20:35]+.12])]:
   self.assertNotEqual(clock_alignment(a,b,1,29)['status'],'aligned')
if __name__=='__main__':unittest.main()

