"""Library inputs shared by command-line and application entry points."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from backend.app.audio.analyze import analyze
from backend.app.planning.rhythm import analyze_rhythm
from backend.app.db import Database

EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aiff', '.aif', '.ogg'}


def discover(inputs):
    paths = []
    for value in inputs:
        path = Path(value).resolve(strict=True)
        if path.is_dir():
            paths.extend(sorted((p for p in path.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS),
                                key=lambda p: p.name.casefold()))
        else:
            if path.suffix.lower() not in EXTENSIONS:
                raise ValueError(f'Unsupported input: {path.name}')
            paths.append(path)
    if not paths:
        raise ValueError('No audio tracks found')
    return paths


def collect_entries(paths, settings, storage):
    entries, errors = [], []
    for index, path in enumerate(paths):
        print(f'Analyzing {index+1}/{len(paths)}: {path.name}', flush=True)
        try:
            analysis = analyze(path, settings, storage)
            analysis['rhythm'] = analyze_rhythm(path, analysis, settings, storage)
            identity = hashlib.sha256(f'{path}:{analysis["content_hash"]}'.encode()).hexdigest()[:16]
            entries.append({'entry_id': f'{index+1:03d}-{identity}', 'path': str(path), 'analysis': analysis})
            print(f'  Local tempo: {analysis["rhythm"]["bpm"]}; usable pulse windows: {len(analysis["rhythm"]["windows"])}', flush=True)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({'path': str(path), 'error': str(exc)})
    if errors:
        report = storage.path('plans', 'analysis-errors-'+uuid4().hex+'.json')
        report.write_text(json.dumps({'errors': errors, 'plan_created': False}, indent=2), encoding='utf-8')
        raise ValueError(f'Input errors prevented plan creation; no reduced playlist was planned. Details: {report}')
    return entries


def persist_plan(entries, plan, settings):
    database = Database(settings.data_root/'app.sqlite3')
    database.initialize()
    database.register_plan(entries, plan)
    return database
