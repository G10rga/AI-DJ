"""Deterministic mixer-style EQ handoffs, independent of track ordering."""
def eq_swap_graph(gains, first_seconds, second_seconds, overlap, bpm, phase=0.0, protect_lead=False, long_blend=False):
    beat = 60 / bpm
    transition = first_seconds - overlap
    expected = first_seconds + second_seconds - overlap
    # Anchor to an actual outgoing beat; halfway through a time window need not
    # be a beat. This is not a claim to know the musical downbeat.
    desired_swap = overlap - beat if protect_lead else overlap / 2
    swap = phase + round((desired_swap - phase) / beat) * beat
    swap = max(beat, min(overlap - beat, swap))
    bass_width = (4 if long_blend else .5) * beat
    mid_width = min((64 if long_blend else 8) * beat, overlap / 2)
    upper_split = 4500 if protect_lead else 1800
    graph = []
    for index, gain in enumerate(gains):
        graph.append(f'[{index}:a]volume={gain:.9f},acrossover=split=180 {upper_split}:order=4th[{index}l][{index}m][{index}h]')
        direction = 'out' if index == 0 else 'in'
        origin = transition if index == 0 else 0
        bands = (
            ('l', swap - bass_width/2, bass_width, 'hsin'),
            ('m', swap - mid_width/2, mid_width, 'hsin'),
            ('h', 0, overlap, 'qsin'),
        )
        if protect_lead:
            bands = (
                bands[0],
                ('m', overlap - beat if index == 0 else overlap, beat, 'hsin'),
                ('h', overlap - 2*beat if index == 0 else 0,
                 2*beat if index == 0 else overlap, 'qsin'),
            )
        for band, begin, width, curve in bands:
            graph.append(f'[{index}{band}]afade=t={direction}:st={origin+begin:.9f}:d={width:.9f}:curve={curve}[{index}{band}f]')
        graph.append(f'[{index}lf][{index}mf][{index}hf]amix=inputs=3:normalize=0[track{index}]')
    delay_samples = round(transition * 44100)
    graph.append(f'[track1]adelay={delay_samples}S:all=1[incoming]')
    # Reset the mixed stream before the final time-based fade. Without this,
    # the native graph can mute the tail when its first source reaches EOF.
    graph.append(f'[track0][incoming]amix=inputs=2:normalize=0:duration=longest,'
                 f'asetpts=N/SR/TB,'
                 f'afade=t=in:d=0.01,afade=t=out:st={expected-.01:.9f}:d=0.01,'
                 f'atrim=duration={expected:.9f}[out]')
    return ';'.join(graph), {
        'name': 'lead_handoff' if protect_lead else 'eq_swap', 'crossover_hz': [180, upper_split],
        'blend_profile': 'long_groove' if long_blend else 'standard',
        'bass_swap_at_seconds': transition + swap,
        'bass_swap_duration_seconds': bass_width,
        'mid_swap_duration_seconds': 2 * beat if protect_lead else mid_width,
        'outgoing_lead_ends_at_seconds': first_seconds if protect_lead else transition + swap + mid_width/2,
        'incoming_lead_starts_at_seconds': first_seconds if protect_lead else transition + swap - mid_width/2,
        'vocal_detection': 'not_performed',
        'phrase_alignment': 'unverified',
    }
