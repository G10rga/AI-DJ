"""Deterministic one-bar loop, stateful filter sweep and beat-synced echo."""
import numpy as np

VERSION='loop-filter-delay-1'


def splice_loop(audio,rate,template_start,loop_start,release,bar_seconds,seam_seconds=.004):
    """Repeat at absolute musical times; crossfade seams without shortening bars."""
    audio=np.asarray(audio,dtype=np.float32)
    if audio.ndim!=2 or audio.shape[1]!=2 or not np.isfinite(audio).all():raise ValueError('Require finite stereo audio')
    values=[rate,template_start,loop_start,release,bar_seconds,seam_seconds]
    if not np.isfinite(values).all() or rate<=0 or bar_seconds<=0 or not 0<seam_seconds<bar_seconds/8:
        raise ValueError('Invalid loop clock or seam')
    if not 0<loop_start<release<len(audio)/rate or template_start-seam_seconds<0 or template_start+bar_seconds+seam_seconds>=len(audio)/rate:
        raise ValueError('Loop lies outside prepared context')
    cycles=(release-loop_start)/bar_seconds
    if abs(cycles-round(cycles))>1e-7:raise ValueError('Release must be on a loop bar boundary')
    output=audio.copy()
    start=round((loop_start-seam_seconds)*rate);stop=round((release+seam_seconds)*rate)
    times=np.arange(start,stop)/rate
    phase=np.mod(times-loop_start,bar_seconds)
    coordinate=(template_start+phase)*rate
    indexes=np.arange(len(audio))
    sample=lambda at:np.column_stack([np.interp(at,indexes,audio[:,channel]) for channel in range(2)])
    repeated=sample(coordinate)
    # Blend the actual tail/head context across each wrap. No overlap-add
    # shortening: every repeated downbeat keeps its absolute sample position.
    delta=np.mod(times-loop_start+bar_seconds/2,bar_seconds)-bar_seconds/2
    mask=abs(delta)<seam_seconds
    weight=(delta[mask]+seam_seconds)/(2*seam_seconds)
    tail=sample((template_start+bar_seconds+delta[mask])*rate)
    head=sample((template_start+delta[mask])*rate)
    repeated[mask]=tail*(1-weight[:,None])+head*weight[:,None]
    # Click-safe splice from/to the source recording, retaining a full-length
    # preparation for independent timing analysis before output gain controls.
    amount=np.minimum(np.clip((times-loop_start+seam_seconds)/(2*seam_seconds),0,1),
                      np.clip((release+seam_seconds-times)/(2*seam_seconds),0,1))
    output[start:stop]=audio[start:stop]*(1-amount[:,None])+repeated*amount[:,None]
    boundaries=[round((loop_start+k*bar_seconds)*rate) for k in range(round(cycles)+1)]
    return output,{'template_start_seconds':template_start,'template_end_seconds':template_start+bar_seconds,
                   'loop_start_seconds':loop_start,'release_seconds':release,'repeats':round(cycles),
                   'bar_seconds':bar_seconds,'boundary_samples':boundaries,'seam_seconds':seam_seconds}


def apply_effects(looped,incoming,rate,start,release,bar_seconds,block_size=128):
    from pedalboard import LowpassFilter,Delay,HighpassFilter,Pedalboard
    if looped.shape!=incoming.shape or looped.ndim!=2 or looped.shape[1]!=2:
        raise ValueError('Require equal stereo preparations')
    if not np.isfinite(looped).all() or not np.isfinite(incoming).all():raise ValueError('Invalid source samples')
    if block_size<1 or not 0<start<release<len(looped)/rate:raise ValueError('Invalid effect timeline')
    beat=bar_seconds/4
    lowpass=LowpassFilter(cutoff_frequency_hz=min(18000.,rate*.45))
    filtered=np.empty_like(looped)
    automation=[]
    for first in range(0,len(looped),block_size):
        last=min(first+block_size,len(looped));time=(first+last)/(2*rate)
        progress=float(np.clip((time-start)/(release-start),0,1))
        cutoff=min(18000.,rate*.45)*(600/min(18000.,rate*.45))**progress
        lowpass.cutoff_frequency_hz=cutoff
        block=lowpass.process(np.ascontiguousarray(looped[first:last].T),rate,reset=first==0)
        if block.shape!=(2,last-first):raise ValueError('Filter buffered unexpected samples')
        filtered[first:last]=block.T
        if first% (block_size*16)==0:automation.append([float(time),float(cutoff)])
    times=np.arange(len(looped))/rate
    effect_amount=np.clip((times-start)/beat,0,1)
    filtered=looped*(1-effect_amount[:,None])+filtered*effect_amount[:,None]
    dry_gain=np.clip((release-times)/(beat/4),0,1).astype(np.float32)
    dry=filtered*dry_gain[:,None]
    # Feed rises over the last two bars; zero input after release lets the
    # plugin's delay state decay instead of resetting or truncating its tail.
    send=np.clip((times-(release-2*bar_seconds))/(2*bar_seconds),0,1)*.22
    send*=dry_gain
    delay=Pedalboard([Delay(delay_seconds=beat,feedback=.30,mix=1.),HighpassFilter(cutoff_frequency_hz=250)])
    # Warm with a stable maximum processing size; a later larger native block
    # can reprepare the plugin and discard delay state. Keep this size fixed.
    delay.process(np.zeros((2,round(rate)),dtype=np.float32),rate,buffer_size=512,reset=True)
    echo=delay.process(np.ascontiguousarray((filtered*send[:,None]).T),rate,buffer_size=512,reset=False).T
    if echo.shape!=looped.shape:raise ValueError('Delay buffered unexpected samples')
    tail_end=release+2*bar_seconds
    tail_gain=np.clip((tail_end-times)/beat,0,1)
    echo*=tail_gain[:,None]
    incoming_gain=np.clip((times-release)/.005,0,1).astype(np.float32)
    incoming_stem=incoming*incoming_gain[:,None]
    result=dry+echo+incoming_stem
    if not np.isfinite(result).all():raise ValueError('Nonfinite effects output')
    return result,{'outgoing':dry,'echo':echo,'incoming':incoming_stem}, {
        'version':VERSION,'filter':'Pedalboard LowpassFilter','filter_hz':[min(18000.,rate*.45),600.],
        'automation_block_frames':block_size,'automation_samples':automation,'filter_state_preserved':True,
        'delay_seconds':beat,'delay_feedback':.30,'delay_send_max':.22,'delay_return_highpass_hz':250.,
        'delay_silent_warmup_seconds':1.,
        'delay_processing_block_frames':512,
        'delay_tail_ends_seconds':tail_end,'incoming_release_seconds':release,
        'incoming_ramp_seconds':.005,'outgoing_fade_seconds':beat/4}
