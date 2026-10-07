param(
  [ValidateSet('Freeze', 'Bind')][string]$Action = 'Freeze',
  [string]$InputPath,
  [Parameter(Mandatory = $true)][string]$OutputDirectory,
  [string]$FreezeDirectory,
  [string]$Project,
  [string]$RunsPath,
  [ValidateSet('development', 'test')][string]$Partition = 'test'
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project-local Python is not prepared.' }
if ($Action -eq 'Freeze') {
  if (-not $InputPath -or $FreezeDirectory -or $Project -or $RunsPath) { throw 'Freeze requires InputPath and OutputDirectory only.' }
  $benchmarkArguments = @('-B', '-m', 'gamingcreator', 'freeze-benchmark', '--input', $InputPath, '--output', $OutputDirectory)
} else {
  if ($InputPath -or -not $FreezeDirectory -or -not $Project -or -not $RunsPath) { throw 'Bind requires FreezeDirectory, Project, RunsPath and OutputDirectory.' }
  $benchmarkArguments = @('-B', '-m', 'gamingcreator', 'bind-benchmark', '--freeze', $FreezeDirectory, '--project', $Project, '--runs', $RunsPath, '--partition', $Partition, '--output', $OutputDirectory)
}
$benchmarkOutputEncoding = $OutputEncoding
$benchmarkConsoleEncoding = [Console]::OutputEncoding
$benchmarkExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  & $pythonPath @benchmarkArguments
  $benchmarkExit = $LASTEXITCODE
} finally {
  Pop-Location
  $OutputEncoding = $benchmarkOutputEncoding
  [Console]::OutputEncoding = $benchmarkConsoleEncoding
}
exit $benchmarkExit
