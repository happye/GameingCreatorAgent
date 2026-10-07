param(
  [Parameter(Mandatory = $true)][string]$Project,
  [string]$InputPath,
  [string]$Config,
  [string]$MaxCostCny,
  [string]$Resume,
  [ValidateRange(1, 86400)][int]$TimeoutSeconds
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$batchArguments = @('-B', '-m', 'gamingcreator', 'prepare-media-batch', '--project', $Project)
if ($Resume) {
  if ($InputPath -or $Config -or $MaxCostCny) { throw 'Resuming a batch must keep the original input, configuration and saved limits.' }
  $batchArguments += @('--resume', $Resume)
} else {
  if (-not $InputPath -or -not $Config -or -not $MaxCostCny) { throw 'A new batch needs InputPath, Config and MaxCostCny per task.' }
  $batchArguments += @('--input', $InputPath, '--config', $Config, '--max-cost-cny', $MaxCostCny)
}
if ($PSBoundParameters.ContainsKey('TimeoutSeconds')) { $batchArguments += @('--timeout-seconds', $TimeoutSeconds) }
$batchOutputEncoding = $OutputEncoding
$batchConsoleEncoding = [Console]::OutputEncoding
$batchExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @batchArguments
  $batchExit = $LASTEXITCODE
} finally {
  Pop-Location
  $OutputEncoding = $batchOutputEncoding
  [Console]::OutputEncoding = $batchConsoleEncoding
}
exit $batchExit
