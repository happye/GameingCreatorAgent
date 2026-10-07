param(
    [string]$InputPath,
    [string]$ReviewDirectory,
    [string]$RecordPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$referenceArguments = @('-B', (Join-Path $PSScriptRoot 'prepare-benchmark-references.py'), '--output', $OutputDirectory)
if ($InputPath) { $referenceArguments += @('--input', $InputPath) }
if ($ReviewDirectory) { $referenceArguments += @('--review-directory', $ReviewDirectory) }
if ($RecordPath) { $referenceArguments += @('--record', $RecordPath) }
$referenceOutputEncoding = $OutputEncoding
$referenceConsoleEncoding = [Console]::OutputEncoding
$referenceExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @referenceArguments
    $referenceExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $referenceOutputEncoding
    [Console]::OutputEncoding = $referenceConsoleEncoding
}
exit $referenceExit
