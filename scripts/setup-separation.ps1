# Optional local separation environment; all large files stay on D:.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$separationRoot = 'D:\AI-DJ-data\separation'
$pythonPath = Join-Path $separationRoot 'venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $separationRoot,'D:\AI-DJ-data\cache\pip','D:\AI-DJ-data\tmp\pip' | Out-Null
$env:TEMP = 'D:\AI-DJ-data\tmp\pip'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = 'D:\AI-DJ-data\cache\pip'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3.12 -m venv (Join-Path $separationRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed' }
}
& $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-separation.txt')
if ($LASTEXITCODE -ne 0) { throw 'Separation dependencies failed to install' }
Push-Location $projectRoot
try {
    & $pythonPath -m scripts.setup_separation --model-dir (Join-Path $separationRoot 'models')
    if ($LASTEXITCODE -ne 0) { throw 'Separation model setup failed' }
} finally {
    Pop-Location
}
