param(
    [Parameter(Mandatory = $true)][string[]]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$inventoryArguments = @('-B', '-m', 'gamingcreator', 'inventory-sources', '--input') + $InputPath + @('--output', $OutputPath)
$inventoryOutputEncoding = $OutputEncoding
$inventoryConsoleEncoding = [Console]::OutputEncoding
$inventoryExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @inventoryArguments
    $inventoryExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $inventoryOutputEncoding
    [Console]::OutputEncoding = $inventoryConsoleEncoding
}
exit $inventoryExit
