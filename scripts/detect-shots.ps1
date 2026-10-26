param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$Run,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$shotArguments = @('-B', '-m', 'gamingcreator', 'detect-shots', '--project', $Project, '--run', $Run, '--output', $OutputPath)
$shotOutputEncoding = $OutputEncoding
$shotConsoleEncoding = [Console]::OutputEncoding
$shotExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @shotArguments
    $shotExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $shotOutputEncoding
    [Console]::OutputEncoding = $shotConsoleEncoding
}
exit $shotExit
