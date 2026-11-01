param(
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter()][string[]]$Run,
    [switch]$AllEligible
)
$ErrorActionPreference = 'Stop'
if ($AllEligible -and $Run) {
    throw '不能同时指定 -Run 与 -AllEligible。'
}
if (-not $AllEligible -and -not $Run) {
    throw '请提供至少一个 -Run，或使用 -AllEligible。'
}
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$proxyArguments = @('-B', '-m', 'gamingcreator', 'make-proxy', '--project', $Project)
if ($AllEligible) {
    $proxyArguments += '--all-eligible'
} else {
    foreach ($item in $Run) {
        $proxyArguments += @('--run', $item)
    }
}
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
