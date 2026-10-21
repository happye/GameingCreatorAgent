param(
    [Parameter(Mandatory = $true)][string]$Coverage,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [string[]]$Stage,
    [string]$MaxAdditionalCostCny
)
# Read-only: write inert directed gap-fill proposal draft under an ignored artifacts dir.
# Never calls a model / launcher.
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$draftArguments = @(
    '-X', 'utf8', '-B',
    (Join-Path $PSScriptRoot 'prepare-directed-gap-fill-draft.py'),
    '--coverage', $Coverage,
    '--output', $OutputDirectory
)
if ($Stage) {
    foreach ($item in $Stage) {
        $draftArguments += @('--stage', $item)
    }
}
if ($MaxAdditionalCostCny) {
    $draftArguments += @('--max-additional-cost-cny', $MaxAdditionalCostCny)
}
$draftOutputEncoding = $OutputEncoding
$draftConsoleEncoding = [Console]::OutputEncoding
$draftExit = 1
Push-Location $repositoryRoot
try {
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $OutputEncoding
    & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @draftArguments
    $draftExit = $LASTEXITCODE
} finally {
    Pop-Location
    $OutputEncoding = $draftOutputEncoding
    [Console]::OutputEncoding = $draftConsoleEncoding
}
exit $draftExit
