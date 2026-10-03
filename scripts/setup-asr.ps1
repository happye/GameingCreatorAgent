param([switch]$CreateLock, [switch]$Offline)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$uvPath = Join-Path $repositoryRoot '.tools/uv/uv.exe'
Push-Location $repositoryRoot
try {
  $common = @('--python', $pythonPath, '--no-python-downloads', '--default-index', 'https://pypi.org/simple')
  if ($Offline) { $common += '--offline' }
  if ($CreateLock) {
    & $uvPath --no-config lock @common
    if ($LASTEXITCODE -ne 0) { throw 'ASR dependency resolution failed; do not assume runtime ready.' }
  }
  & $uvPath --no-config sync --locked --extra asr --no-build @common
  if ($LASTEXITCODE -ne 0) { throw 'ASR wheel installation failed; no native/model readiness is implied.' }
} finally { Pop-Location }
