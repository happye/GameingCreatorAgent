param(
  [Parameter(Mandatory = $true)][string]$Video,
  [string]$Project = 'artifacts/demo-phase0',
  [string]$Config = 'config.example.json',
  [string]$MaxCostCny = '5',
  [string]$Resume,
  [ValidateRange(1, 86400)][int]$TimeoutSeconds = 3600
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project-local Python is not prepared.' }
if ($Resume -and ($PSBoundParameters.ContainsKey('Config') -or $PSBoundParameters.ContainsKey('MaxCostCny'))) {
  throw 'Resuming preparation must preserve the original configuration and cost limit.'
}
$taskOutputEncoding = $OutputEncoding
$taskConsoleEncoding = [Console]::OutputEncoding
$taskExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  $taskArguments = @('-B', '-m', 'gamingcreator', 'prepare-media', $Video, '--project', $Project, '--timeout-seconds', $TimeoutSeconds)
  if ($Resume) { $taskArguments += @('--resume', $Resume) }
  else { $taskArguments += @('--config', $Config, '--max-cost-cny', $MaxCostCny) }
  & $pythonPath @taskArguments
  $taskExit = $LASTEXITCODE
} finally {
  $OutputEncoding = $taskOutputEncoding
  [Console]::OutputEncoding = $taskConsoleEncoding
  Pop-Location
}
exit $taskExit
