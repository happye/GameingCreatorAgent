param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
& (Join-Path $PSScriptRoot 'setup-env.ps1') -Offline:$Offline
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$uvPath = Join-Path $repositoryRoot '.tools/uv/uv.exe'
Push-Location $repositoryRoot
try {
  $common = @('--python', $pythonPath, '--no-python-downloads', '--default-index', 'https://pypi.org/simple')
  $modelArguments = @()
  if ($Offline) { $common += '--offline'; $modelArguments += '--offline' }
  & $uvPath --no-config sync --locked --extra asr --extra retrieval --no-build @common
  if ($LASTEXITCODE -ne 0) { throw 'Demo dependency synchronization failed.' }
  foreach ($assetScript in @('prepare-asr-assets.py', 'prepare-embedding-assets.py')) {
    & $pythonPath -I -B (Join-Path $PSScriptRoot $assetScript) @modelArguments
    if ($LASTEXITCODE -ne 0) { throw "Pinned project-local assets unavailable: $assetScript" }
  }
  Write-Host 'Demo packages, model weights and runtime libraries are ready inside this repository. Run init.ps1 to check the separately prepared FFmpeg.'
} finally { Pop-Location }
