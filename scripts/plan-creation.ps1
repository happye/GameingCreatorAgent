param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string[]]$Run,
    [Parameter(Mandatory = $true)][string]$Brief,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string[]]$Event = @(),
    [int]$Fps = 30,
    [ValidateSet('chronological', 'hook-first', 'reverse')][string]$Select
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$creationArguments = @('-B', '-m', 'gamingcreator', 'plan-creation', '--project', $Project, '--run') + $Run + @('--brief', $Brief, '--output', $OutputPath, '--fps', "$Fps")
if ($Event.Count -gt 0) { $creationArguments += @('--event') + $Event }
if ($Select) { $creationArguments += @('--select', $Select) }
$previousOutputEncoding = $OutputEncoding
$previousConsoleEncoding = [Console]::OutputEncoding
$creationExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @creationArguments
    $creationExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $previousOutputEncoding
    [Console]::OutputEncoding = $previousConsoleEncoding
}
exit $creationExit
