# Reproducible local tools; large dependencies stay on D: beside the audio cache.
$ErrorActionPreference = 'Stop'
$playlistRoot = if ($env:AI_DJ_DATA_ROOT) { $env:AI_DJ_DATA_ROOT } else { 'D:\AI-DJ-data' }
$playlistTools = Join-Path $playlistRoot 'tools'
$rubberRoot = Join-Path $playlistTools 'rubberband'
New-Item -ItemType Directory -Force $rubberRoot | Out-Null
$release = Join-Path $rubberRoot 'release.zip'
Invoke-WebRequest 'https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip' -OutFile $release
if ((Get-FileHash -LiteralPath $release -Algorithm SHA256).Hash -ne 'F2D47FC64DBB42F6CC62EDF7933AC4FA89D8F0EF8B9CF97B6AFC263A7FE05644') {
    throw 'Unexpected Rubber Band release checksum'
}
Expand-Archive -LiteralPath $release -DestinationPath $rubberRoot -Force
$compiler = Join-Path $playlistTools 'playlist-dsp'
& npm install --prefix $compiler 'assemblyscript@0.28.9' --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'DSP compiler setup failed' }
$project = Split-Path -Parent $PSScriptRoot
& node (Join-Path $compiler 'node_modules/assemblyscript/bin/asc.js') (Join-Path $project 'backend/app/playlist/dsp.ts') --outFile (Join-Path $project 'backend/app/web_assets/playlist-dsp.wasm') --optimize --runtime stub --exportRuntime
if ($LASTEXITCODE -ne 0) { throw 'DSP compilation failed' }
