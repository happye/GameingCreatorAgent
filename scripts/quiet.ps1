# Run a long check quietly: full output goes to a log file, the console gets only a short summary.
# Usage (repo root):
#   ./scripts/quiet.ps1 test-affected [-Browser ...]   # any scripts/<name>.ps1 and its arguments
#   ./scripts/quiet.ps1 verify
#   ./scripts/quiet.ps1 pytest tests/test_x.py::test_y  # plain pytest node IDs / files
# Prints: selection, pass/fail counts, up to 30 FAILED/ERROR node IDs, the log path, and a file of
# failing node IDs for a targeted rerun:  ./scripts/quiet.ps1 pytest (Get-Content <failed-file>)
# Read the log only for the failures you are fixing. Never start a second pytest while one runs:
# the shared basetemp is wiped at start and the other run fails with FileNotFoundError.
param(
  [Parameter(Mandatory = $true, Position = 0)][string]$Name,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root '.cache/test-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $logs ($Name + '-' + $stamp + '.log')
$err = Join-Path $logs ($Name + '-' + $stamp + '.err.log')
$failedFile = Join-Path $logs ($Name + '-' + $stamp + '-failed.txt')
# Single quotes: Start-Process does not escape double quotes, so Windows argument parsing would
# strip them and split "a or b" into separate arguments.
$quoted = @($Rest | Where-Object { $_ } | ForEach-Object { if ($_ -match '[\s''"]') { "'" + ($_ -replace "'", "''") + "'" } else { $_ } })
if ($Name -eq 'pytest') {
  $command = '. ./scripts/env.ps1; python -B -m pytest -p no:cacheprovider -rfE ' + ($quoted -join ' ')
} else {
  $script = Join-Path $PSScriptRoot ($Name + '.ps1')
  if (-not (Test-Path -LiteralPath $script)) { throw "No script scripts/$Name.ps1" }
  $command = '& ''' + $script + ''' ' + ($quoted -join ' ')
}
# A separate process with process-level redirection: Windows PowerShell 5.1 would otherwise turn
# native stderr lines (uv "Resolved ...") into terminating errors.
. (Join-Path $PSScriptRoot 'test-run-lock.ps1')
$lock = Enter-TestRunLock $root ($Name + ' ' + ($Rest -join ' '))
$started = Get-Date
try {
  $process = Start-Process -FilePath 'powershell.exe' -WorkingDirectory $root -NoNewWindow -Wait -PassThru `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command) `
    -RedirectStandardOutput $out -RedirectStandardError $err
} finally { Exit-TestRunLock $lock }
$seconds = [int]((Get-Date) - $started).TotalSeconds
$lines = @(Get-Content -LiteralPath $out, $err -Encoding utf8 -ErrorAction SilentlyContinue)
$failed = @($lines | Where-Object { $_ -match '^(FAILED|ERROR) (\S+\.py(::\S+)?)' } | ForEach-Object { ($_ -split ' ')[1] } | Sort-Object -Unique)
if ($failed.Count) { $failed | Set-Content -LiteralPath $failedFile -Encoding utf8 }
Write-Output ("== $Name exit=" + $process.ExitCode + " in ${seconds}s")
$lines | Where-Object { $_ -match '^selection:|\d+ (passed|failed|error)|no tests ran|^ERROR: |^All project checks passed|Project check failed|Last full verify|Exception:' } |
  Select-Object -Last 8 | ForEach-Object { Write-Output ('  ' + $_.Trim()) }
if ($failed.Count) {
  Write-Output ("  failing node IDs: " + $failed.Count + " (first 30 below) -> " + $failedFile)
  $failed | Select-Object -First 30 | ForEach-Object { Write-Output ('    ' + $_) }
}
Write-Output ("  log: " + $out)
exit $process.ExitCode
