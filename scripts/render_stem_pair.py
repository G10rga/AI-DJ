"""Render a local mid-song vocal handoff from a validated pair report."""
import argparse
import json
from pathlib import Path
import subprocess
from uuid import uuid4
import numpy as np
from backend.app.audio.mdx import sha256_file
from backend.app.audio.phase import pulse_grid, compare_grids, check_overlap_windows
from backend.app.audio.probe import probe, run_audio
from backend.app.audio.stem_mix import vocal_schedule, stem_pair_graph
from backend.app.audio.stretch import prepare_excerpt, pcm_rms, pcm_peak, float_pcm_peak
from backend.app.config import Settings
from backend.app.storage import Storage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pair_report', type=Path)
    parser.add_argument('--separator-python', type=Path, default=Path('D:/AI-DJ-data/separation/venv/Scripts/python.exe'))
    parser.add_argument('--model-dir', type=Path, default=Path('D:/AI-DJ-data/separation/models'))
    parser.add_argument('--stem-cache', type=Path, default=Path('D:/AI-DJ-data/separation/stems'))
    parser.add_argument('--vocal-fade-bars', type=int, choices=(2, 4, 8), default=4)
    parser.add_argument('--blend-profile', choices=('standard', 'long_groove'), default='standard')
    parser.add_argument('--result-file', type=Path, help='Write the output/report paths for a calling job')
    parser.add_argument('--learned-settings', action='store_true', help='Use the explicit-feedback ranker when ready; DSP checks still apply')
    args = parser.parse_args()
    reference = json.loads(args.pair_report.read_text(encoding='utf-8'))
    settings = Settings.from_env()
    preference_selection=None
    if args.learned_settings:
        from backend.app.planning.preferences import PreferenceStore
        preference_selection=PreferenceStore(settings.data_root/'feedback').settings(reference,args.vocal_fade_bars,args.blend_profile)
        args.vocal_fade_bars=preference_selection['fade_bars'];args.blend_profile=preference_selection['profile']
        print('Preference selection:',json.dumps(preference_selection),flush=True)
    storage = Storage(settings.data_root)
    storage.initialize()
    cues = reference['tracks']
    if len(cues) != 2 or not reference['target_bpm'] or reference['style'] == 'boundary_fade':
        raise ValueError('Use a validated beatmatched pair report')
    first, second = [cue['output_seconds'] for cue in cues]
    if not all(np.isfinite(x) and 2 < x <= 180 for x in (first, second)):
        raise ValueError('Stem experiment supports excerpts of 2–180 seconds')
    overlap = reference['overlap_seconds']
    transition = first-overlap
    expected = first+second-overlap
    name = 'stem-pair-'+uuid4().hex
    destination = storage.path('renders', name+'.mp3')
    report_path = storage.path('renders', name+'.json')
    storage.require_space(int((first+second)*44100*2*4*12), settings.min_free_bytes)
    with storage.temporary_directory() as temporary:
        prepared, stems = [], []
        for index, cue in enumerate(cues):
            source = Path(cue['path'])
            if sha256_file(source) != cue['content_hash']:
                raise ValueError('Source changed since the validated beatmatched report')
            output = temporary/f'source-{index}.wav'
            prepare_excerpt(source, output, cue['source_in'], cue['source_out'], cue['source_bpm'], cue['target_bpm'], settings)
            prepared.append(output)
            pointer = temporary/f'stems-{index}.json'
            print(f'Separating {source.name}', flush=True)
            subprocess.run([str(args.separator_python), '-m', 'scripts.separate_vocals', str(output),
                            '--model-dir', str(args.model_dir), '--cache-root', str(args.stem_cache),
                            '--result-file', str(pointer)], check=True, timeout=1800,
                           cwd=str(Path(__file__).resolve().parents[1]))
            stem = json.loads(pointer.read_text(encoding='utf-8'))
            if abs(stem['frames']/44100-cue['output_seconds']) > .005:
                raise ValueError('Separated stem duration differs from prepared source')
            stems.append(stem)
        first_grid = pulse_grid(prepared[0], transition, min(30, overlap), 60/reference['target_bpm'])
        second_grid = pulse_grid(prepared[1], 0, min(30, overlap), 60/reference['target_bpm'])
        alignment = compare_grids(first_grid, second_grid, overlap)
        if abs(alignment['incoming_delay_seconds']) > .012 or abs(alignment['drift_seconds']) > .025:
            raise ValueError('Reference cues no longer satisfy beat alignment')
        instrument_grids, instrument_pcm = [], []
        for index, stem in enumerate(stems):
            pulse_pcm = temporary/f'instrument-pulse-{index}.wav'
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', stem['instrumental'],
                       '-c:a', 'pcm_s16le', str(pulse_pcm)])
            instrument_pcm.append(pulse_pcm)
            instrument_grids.append(pulse_grid(pulse_pcm, transition if index == 0 else 0,
                                              min(30, overlap), 60/reference['target_bpm']))
        instrumental_alignment = compare_grids(*instrument_grids, overlap)
        if abs(instrumental_alignment['incoming_delay_seconds']) > .015 or abs(instrumental_alignment['drift_seconds']) > .025:
            raise ValueError('Separated instrumentals do not preserve acceptable beat alignment')
        windowed_alignment = check_overlap_windows(*instrument_pcm, transition, overlap, reference['target_bpm']) if overlap > 30 else []
        levels = [pcm_rms(prepared[0], transition, overlap), pcm_rms(prepared[1], 0, overlap)]
        safe = [min(1, .85/max(pcm_peak(path), 1e-8)) for path in prepared]
        level = min(a*b for a, b in zip(levels, safe))
        gains = [min(gain, level/max(rms, 1e-8)) for gain, rms in zip(safe, levels)]
        schedule = vocal_schedule(stems[0]['vocals'], stems[1]['vocals'], transition, overlap,
                                  reference['target_bpm'], fade_bars=args.vocal_fade_bars)
        print('Vocal schedule:', json.dumps({k:v for k,v in schedule.items() if 'regions' not in k}), flush=True)
        graph, recipe = stem_pair_graph(gains, first, second, overlap, reference['target_bpm'], first_grid['phase_seconds'],
                                        schedule, blend_profile=args.blend_profile)
        inputs = [stems[0]['instrumental'], stems[1]['instrumental'], stems[0]['vocals'], stems[1]['vocals']]
        command = [settings.ffmpeg, '-v', 'error', '-nostdin']
        for path in inputs:
            command += ['-i', path]
        raw = temporary/'mixed.f32'
        run_audio(command+['-filter_complex', graph, '-map', '[out]', '-f', 'f32le', str(raw)])
        peak = float_pcm_peak(raw)
        gain = min(1, .82/max(peak, 1e-8))
        mixed = temporary/'mixed.mp3'
        run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-f', 'f32le', '-ar', '44100', '-ac', '2',
                   '-i', str(raw), '-af', f'volume={gain:.12f}', '-c:a', 'libmp3lame', '-b:a', '256k', str(mixed)])
        info = probe(mixed, settings)
        if info.channels != 2 or abs(info.duration-expected) > .15:
            raise ValueError('Output duration or stereo validation failed')
        decoded = temporary/'check.f32'
        run_audio([settings.ffmpeg, '-v', 'error', '-xerror', '-i', str(mixed), '-ar', '44100', '-ac', '2', '-f', 'f32le', str(decoded)])
        samples = np.memmap(decoded, dtype='<f4', mode='r').reshape(-1, 2)
        final_peak = float(np.max(abs(samples)))
        if not np.all(np.isfinite(samples)) or final_peak >= 1:
            raise ValueError('Encoded preview contains invalid or clipped samples')
        energy = [float(np.sqrt(np.mean(samples[t*44100:(t+2)*44100]**2))) for t in range(0, int(expected)-2, 2)]
        if any(value < 1e-4 for value in energy):
            raise ValueError('Unexpected silent window in mid-song stem preview')
        del samples
        report = {'output': str(destination), 'reference_pair_report': str(args.pair_report.resolve()),
                  'style': 'vocal_stem_handoff', 'preference_selection':preference_selection,'duration': info.duration, 'target_bpm': reference['target_bpm'],
                  'tracks': cues, 'transition_at_seconds': transition, 'overlap_seconds': overlap,
                  'pulse_alignment': alignment, 'instrumental_pulse_alignment': instrumental_alignment,
                  'windowed_instrumental_alignment': windowed_alignment,
                  'recipe': recipe, 'stems': stems,
                  'track_gains': gains, 'mixed_pcm_peak': peak, 'post_mix_gain': gain,
                  'encoded_peak': final_peak, 'energy_rms_2s': energy,
                  'warnings': ['Pretrained source separation can leave vocal bleed and introduce artifacts.',
                               'Vocal gaps are energy heuristics, not semantic lyric boundaries; owner listening required.']}
        staged = temporary/'report.json'
        staged.write_text(json.dumps(report, indent=2), encoding='utf-8')
        mixed.replace(destination)
        staged.replace(report_path)
    print(f'Audio: {destination}\nReport: {report_path}', flush=True)
    if args.result_file:
        args.result_file.write_text(json.dumps({'output': str(destination), 'report': str(report_path)}), encoding='utf-8')


if __name__ == '__main__':
    main()
