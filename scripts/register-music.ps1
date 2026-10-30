param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$SourceDescription,
    [ValidateSet('unknown', 'user_declared', 'test_only')][string]$LicenseStatus = 'unknown',
    [string]$LicenseEvidence
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$musicArguments = @('-B', '-m', 'gamingcreator', 'register-music', '--input', $InputPath, '--title', $Title, '--source-description', $SourceDescription, '--license-status', $LicenseStatus)
if ($LicenseEvidence) { $musicArguments += @('--license-evidence', $LicenseEvidence) }
$previousOutputEncoding = $OutputEncoding
$previousConsoleEncoding = [Console]::OutputEncoding
$musicExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @musicArguments
    $musicExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $previousOutputEncoding
    [Console]::OutputEncoding = $previousConsoleEncoding
}
exit $musicExit
