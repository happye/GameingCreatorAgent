param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$Run
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$proxyArguments = @('-B', '-m', 'gamingcreator', 'make-proxy', '--project', $Project, '--run', $Run)
$proxyOutputEncoding = $OutputEncoding
$proxyConsoleEncoding = [Console]::OutputEncoding
$proxyExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @proxyArguments
    $proxyExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $proxyOutputEncoding
    [Console]::OutputEncoding = $proxyConsoleEncoding
}
exit $proxyExit
