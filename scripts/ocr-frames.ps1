param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$Run,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [int]$Every = 1
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$ocrArguments = @('-B', '-m', 'gamingcreator', 'ocr-frames', '--project', $Project, '--run', $Run, '--output', $OutputPath, '--every', $Every)
$ocrOutputEncoding = $OutputEncoding
$ocrConsoleEncoding = [Console]::OutputEncoding
$ocrExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @ocrArguments
    $ocrExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $ocrOutputEncoding
    [Console]::OutputEncoding = $ocrConsoleEncoding
}
exit $ocrExit
