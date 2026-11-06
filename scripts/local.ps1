# Project-local launcher. Keeps large audio files off C: without changing global settings.
$ErrorActionPreference = 'Stop'
$env:AI_DJ_FFMPEG = 'D:\Tools\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
$env:AI_DJ_FFPROBE = 'D:\Tools\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe'
$env:AI_DJ_DATA_ROOT = 'D:\AI-DJ-data'
$env:NUMBA_CACHE_DIR = 'D:\AI-DJ-data\cache\numba'
$env:JOBLIB_TEMP_FOLDER = 'D:\AI-DJ-data\tmp'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the virtual environment first: python -m venv .venv'
}

Push-Location $projectRoot
try {
    if ($args.Count -eq 0) {
        & $pythonPath -m scripts.doctor
    } else {
        & $pythonPath @args
    }
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
