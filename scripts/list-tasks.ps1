param(
  [string]$Project = 'artifacts/demo-phase0',
  [string]$Run,
  [ValidateRange(1, 200)][int]$Limit = 100,
  [ValidateRange(0, 1000000)][int]$Offset = 0,
  [switch]$Json
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project-local Python is not prepared.' }
$taskOutputEncoding = $OutputEncoding
$taskConsoleEncoding = [Console]::OutputEncoding
$taskExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  $taskArguments = @('-B', '-m', 'gamingcreator', 'tasks', '--project', $Project, '--limit', $Limit, '--offset', $Offset)
  if ($Run) { $taskArguments += @('--run', $Run) }
  $taskResult = & $pythonPath @taskArguments
  $taskExit = $LASTEXITCODE
  if ($taskExit -eq 0) {
    if ($Json) { Write-Output $taskResult }
    else {
      $taskPage = $taskResult | ConvertFrom-Json
      Write-Output ('Saved tasks: ' + $taskPage.total + '; showing ' + $taskPage.tasks.Count + ' from offset ' + $taskPage.offset)
      $taskPage.tasks | Select-Object @{Name='Source';Expression={$_.sourceName}},@{Name='Progress';Expression={$_.phaseLabel}},@{Name='Frames';Expression={$_.imageCount}},@{Name='Events';Expression={$_.eventCount}},@{Name='Known CNY';Expression={$_.cost.knownCny}},@{Name='Unknown attempts';Expression={$_.cost.unknownAttempts}},@{Name='Unknown reserve CNY';Expression={if ($null -eq $_.cost.unknownReservationCny) {'unverified'} else {$_.cost.unknownReservationCny}}},runId | Format-Table -AutoSize
      Write-Output 'Saved progress only; viewing does not start or resume analysis. Cost estimates and unknown reserves remain separate.'
      if ($Run) { $taskPage.tasks | ConvertTo-Json -Depth 12 }
    }
  }
} finally {
  $OutputEncoding = $taskOutputEncoding
  [Console]::OutputEncoding = $taskConsoleEncoding
  Pop-Location
}
exit $taskExit
