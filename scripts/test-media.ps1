param(
  [string]$SourcePath,
  [switch]$AllLocal,
  [ValidateRange(1, 1000000)][int]$MaxFrames = 1000,
  [ValidateRange(1, 86400000)][int]$SamplingIntervalMs = 1000,
  [ValidateRange(1, 86400)][int]$TimeoutSeconds = 180
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
Assert-ProjectMediaTools -RepositoryRoot $repositoryRoot
if (($AllLocal -and $SourcePath) -or (-not $AllLocal -and -not $SourcePath)) { throw 'Choose -AllLocal or -SourcePath.' }
$arguments = @('--input', $SourcePath)
if ($AllLocal) { $arguments = @('--all-local') }
$arguments += @('--max-frames', $MaxFrames, '--interval-ms', $SamplingIntervalMs, '--timeout-seconds', $TimeoutSeconds)
& (Join-Path $repositoryRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'validate-media.py') @arguments
exit $LASTEXITCODE
