param([string]$DataRoot = 'D:\AI-DJ-data')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$timelineRoot = Join-Path $DataRoot 'timeline'
$timelinePython = Join-Path $timelineRoot 'venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $timelineRoot,(Join-Path $DataRoot 'cache\pip'),(Join-Path $DataRoot 'tmp\timeline') | Out-Null
$env:TEMP = Join-Path $DataRoot 'tmp\timeline'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $DataRoot 'cache\pip'
$env:HF_HOME = Join-Path $timelineRoot 'hf-cache'
$env:TORCH_HOME = Join-Path $timelineRoot 'torch-cache'
if (-not (Test-Path -LiteralPath $timelinePython)) {
    py -3.12 -m venv (Join-Path $timelineRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Timeline environment creation failed' }
}
& $timelinePython -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'CPU PyTorch installation failed' }
& $timelinePython -m pip install -r (Join-Path $projectRoot 'requirements-timeline-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Timeline dependencies failed' }
Push-Location $projectRoot
try {
    & $timelinePython -m scripts.setup_timeline --root $timelineRoot
    if ($LASTEXITCODE -ne 0) { throw 'Timeline model setup failed' }
} finally { Pop-Location }
