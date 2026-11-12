"""Verify encoded audio preserves the actual pre-encode waveform's timebase."""
import numpy as np
import soundfile as sf
from scipy.signal import correlate,correlation_lags

def verify_encoding(reference,encoded,start,end):
    rows=[]
    with sf.SoundFile(reference) as a,sf.SoundFile(encoded) as b:
        if a.samplerate!=44100 or b.samplerate!=44100 or a.channels!=2 or b.channels!=2:
            raise ValueError('Encoding timing requires 44100Hz stereo PCM')
        for left in np.arange(start,end,2.):
            count=round(min(2.,end-left)*44100)
            if count<4410:continue
            a.seek(round(left*44100));b.seek(round(left*44100))
            x=a.read(count,dtype='float32',always_2d=True)[::4].astype(float)
            y=b.read(count,dtype='float32',always_2d=True)[::4].astype(float)
            if x.shape!=y.shape:return {'status':'mismatch','reason':'PCM duration differs'}
            denominator=np.linalg.norm(x)*np.linalg.norm(y)
            if denominator<1e-9:return {'status':'unknown','reason':'Silent encoding comparison'}
            correlations=sum(correlate(y[:,i],x[:,i],mode='full',method='fft') for i in (0,1))
            lags=correlation_lags(len(x),len(y));mask=abs(lags)<=.6*11025
            lag=int(lags[mask][np.argmax(correlations[mask])]);similarity=float(np.sum(x*y)/denominator)
            rows.append({'start_seconds':float(left),'duration_seconds':count/44100,
                         'lag_seconds':lag/11025,'zero_lag_similarity':similarity})
    return {'version':'encoded-waveform-timebase-1','status':'aligned' if rows and all(abs(r['lag_seconds'])<=.001 and r['zero_lag_similarity']>=.98 for r in rows) else 'mismatch',
            'maximum_lag_seconds':.001,'minimum_similarity':.98,'windows':rows}
