"""The same sample-based relative master gains for Generate and Compare."""
import numpy as np


def relative_gain(plan, source_index, times):
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or not np.isfinite(times).all():
        raise ValueError('Invalid automation sample positions')
    gain = np.ones(len(times), dtype=np.float64)
    if source_index:
        join = plan['joins'][source_index-1]
        entry, fade, end = (join[k] for k in ('entry_seconds', 'fade_start_seconds', 'end_seconds'))
        if join['candidate']['recipe'] == 'protected_vocal':
            incoming = np.where(times < fade, .25*np.clip((times-entry)/(fade-entry), 0, 1),
                .25+.75*np.clip((times-fade)/(end-fade), 0, 1))
        elif join['candidate']['recipe'] == 'plain_crossfade':
            incoming = np.clip((times-entry)/(end-entry), 0, 1)
        else:
            raise ValueError('Unsupported incoming recipe')
        gain *= incoming
    if source_index < len(plan['joins']):
        join = plan['joins'][source_index]
        fade, end = join['fade_start_seconds'], join['end_seconds']
        gain *= 1-np.clip((times-fade)/(end-fade), 0, 1)
    return gain.astype(np.float32)
