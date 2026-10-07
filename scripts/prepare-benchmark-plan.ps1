param(
    [string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$planEditorArguments = @('-B', (Join-Path $PSScriptRoot 'prepare-benchmark-plan.py'), '--output', $OutputDirectory)
if ($InputPath) { $planEditorArguments += @('--input', $InputPath) }
$planEditorOutputEncoding = $OutputEncoding
$planEditorConsoleEncoding = [Console]::OutputEncoding
$planEditorExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @planEditorArguments
    $planEditorExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $planEditorOutputEncoding
    [Console]::OutputEncoding = $planEditorConsoleEncoding
}
exit $planEditorExit
