param([string]$SourcePath, [switch]$AllLocal)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
Assert-ProjectMediaTools -RepositoryRoot $repositoryRoot
if (($AllLocal -and $SourcePath) -or (-not $AllLocal -and -not $SourcePath)) { throw 'Choose -AllLocal or -SourcePath.' }
$arguments = @('--input', $SourcePath)
if ($AllLocal) { $arguments = @('--all-local') }
& (Join-Path $repositoryRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'validate-storage.py') @arguments
exit $LASTEXITCODE
