"""Loop timing, seam preservation, stateful native effects and echo flushing."""
import importlib.util
import unittest
import numpy as np
from backend.app.research.loop_effects import splice_loop,apply_effects


class LoopClockTests(unittest.TestCase):
    def test_fractional_bar_lengths_keep_absolute_grid_and_stereo_channels(self):
        rate=8000;bar=.95371;entry=2.;release=entry+4*bar
        times=np.arange(8*rate)/rate
        audio=np.column_stack([.1*np.sin(2*np.pi*100*times),.03*np.cos(2*np.pi*237*times)]).astype(np.float32)
        output,report=splice_loop(audio,rate,3.,entry,release,bar)
        self.assertEqual(output.shape,audio.shape)
        self.assertEqual(report['repeats'],4)
        for i,boundary in enumerate(report['boundary_samples']):
            self.assertLessEqual(abs(boundary/rate-(entry+i*bar)),.5/rate)
        np.testing.assert_array_equal(output[:round((entry-.004)*rate)],audio[:round((entry-.004)*rate)])
        np.testing.assert_array_equal(output[round((release+.004)*rate):],audio[round((release+.004)*rate):])
        self.assertFalse(np.allclose(output[:,0],output[:,1]))

    def test_splice_smooths_discontinuous_template_without_changing_duration(self):
        rate=8000;times=np.arange(8*rate)/rate
        audio=np.column_stack([np.sin(2*np.pi*63.25*times)]*2).astype(np.float32)*.2
        output,_=splice_loop(audio,rate,1.,2.,6.,1.)
        for boundary in (3*rate,4*rate,5*rate):
            jump=float(np.max(abs(output[boundary]-output[boundary-1])))
            self.assertLess(jump,.04)
        self.assertEqual(len(output),len(audio))

    def test_invalid_release_missing_context_or_nonfinite_audio_fail(self):
        audio=np.zeros((8000*8,2),dtype=np.float32)
        with self.assertRaises(ValueError):splice_loop(audio,8000,1.,2.,5.5,1.)
        with self.assertRaises(ValueError):splice_loop(audio,8000,0.,2.,6.,1.)
        audio[0,0]=np.nan
        with self.assertRaises(ValueError):splice_loop(audio,8000,1.,2.,6.,1.)


@unittest.skipUnless(importlib.util.find_spec('pedalboard'),'Run native DSP tests in the isolated Pedalboard runtime')
class NativeEffectTests(unittest.TestCase):
    def test_filter_sweep_attenuates_highs_and_keeps_delay_tail_after_release(self):
        rate=8000;times=np.arange(10*rate)/rate
        audio=np.column_stack([.1*np.sin(2*np.pi*2000*times)]*2).astype(np.float32)
        incoming=np.zeros_like(audio)
        output,stems,recipe=apply_effects(audio,incoming,rate,2.,6.,1.)
        rms=lambda piece:float(np.sqrt(np.mean(piece.astype(float)**2)))
        early=rms(stems['outgoing'][round(2.3*rate):round(2.8*rate)])
        late=rms(stems['outgoing'][round(5.3*rate):round(5.8*rate)])
        self.assertLess(late,.7*early)
        self.assertGreater(rms(stems['echo'][6*rate:7*rate]),1e-5)
        self.assertEqual(float(abs(stems['echo'][8*rate:]).max()),0.)
        self.assertTrue(np.isfinite(output).all())
        self.assertEqual(recipe['delay_seconds'],.25)

    def test_delay_impulse_is_on_the_requested_beat_and_survives_buffer_calls(self):
        from pedalboard import Delay
        rate=8000;delay=Delay(delay_seconds=.5,feedback=.3,mix=1.)
        # Keep the maximum native block size stable across calls, matching
        # the renderer even when caller buffer lengths differ.
        delay.process(np.zeros((2,rate),dtype=np.float32),rate,buffer_size=512,reset=True)
        first=np.zeros((2,rate//4),dtype=np.float32);first[:,0]=.1
        a=delay.process(first,rate,buffer_size=512,reset=False)
        b=delay.process(np.zeros((2,rate*2),dtype=np.float32),rate,buffer_size=512,reset=False)
        result=np.concatenate([a,b],axis=1)
        self.assertLessEqual(abs(int(np.argmax(abs(result[0])))-rate//2),1)
        self.assertGreater(abs(result[0,rate]),.001)


if __name__=='__main__':unittest.main()
