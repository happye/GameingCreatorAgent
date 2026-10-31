param(
    [Parameter(Mandatory=$true)][string[]]$RelativeFile,
    [switch]$Apply,
    [int]$MinimumAgeHours = 24
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$python=Join-Path $repoRoot '.venv/Scripts/python.exe'
$cache=Join-Path $repoRoot '.cache'
$lock=[IO.File]::Open((Join-Path $cache 'reclamation.lock'),'OpenOrCreate','ReadWrite','None')
try {
    $active=@(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^ffmpeg|^pytest' -or ($_.Name -match '^python' -and $_.CommandLine -match 'pytest')
    })
    if ($active.Count) { throw 'Active test/media process; manual reclamation refused.' }
    $gcArgs=@('-B',(Join-Path $PSScriptRoot 'cache-maintenance.py'),'--relative-file') + $RelativeFile
    $gcArgs+=@('--minimum-age-hours',[string]$MinimumAgeHours)
    if ($Apply) { $gcArgs+='--apply' }
    & $python @gcArgs
    if ($LASTEXITCODE -ne 0) { throw 'Cache reclamation refused or failed.' }
} finally { $lock.Dispose() }
