# Tier 1 tests: run only the pytest files affected by the current change (see testing-guide.md).
# Usage: ./scripts/test-affected.ps1 [-Base <git ref>] [-ListOnly] [-Browser] [-Deep] [-PytestArgs '-x -rfE']
# -PytestArgs is split on spaces/commas (works the same from powershell -File); use affected_tests.py for quoted options.
[CmdletBinding(PositionalBinding = $false)]
param([string]$Base = 'HEAD', [switch]$ListOnly, [switch]$Browser, [switch]$Deep, [string[]]$PytestArgs)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$arguments = @('-B', (Join-Path $PSScriptRoot 'affected_tests.py'), '--base', $Base)
if (-not $ListOnly) { $arguments += '--run' }
if ($Browser) { $arguments += '--browser' }
if ($Deep) { $arguments += '--deep' }
$extra = @($PytestArgs | ForEach-Object { $_ -split '[\s,]+' } | Where-Object { $_ })
if ($extra) { $arguments += '--'; $arguments += $extra }
Push-Location $repositoryRoot
try {
  & $pythonPath @arguments
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
