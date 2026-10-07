param(
  [Parameter(Mandatory = $true)][string]$Project,
  [Parameter(Mandatory = $true)][string]$ReportPath,
  [Parameter(Mandatory = $true)][string]$BindingDirectory,
  [Parameter(Mandatory = $true)][string]$OutputDirectory,
  [string]$RecordPath
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$reviewArguments = @('-B', (Join-Path $PSScriptRoot 'prepare-benchmark-review.py'), '--project', $Project, '--report', $ReportPath, '--binding', $BindingDirectory, '--output', $OutputDirectory)
if ($RecordPath) { $reviewArguments += @('--record', $RecordPath) }
$reviewOutputEncoding = $OutputEncoding
$reviewConsoleEncoding = [Console]::OutputEncoding
$reviewExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  & $pythonPath @reviewArguments
  $reviewExit = $LASTEXITCODE
} finally {
  Pop-Location
  $OutputEncoding = $reviewOutputEncoding
  [Console]::OutputEncoding = $reviewConsoleEncoding
}
exit $reviewExit
