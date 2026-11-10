# One pytest run per working tree: the shared basetemp (.cache/pytest-tmp-run) is wiped when a run
# starts, so a second concurrent run makes the first fail en masse with FileNotFoundError.
# Dot-source, then: $lock = Enter-TestRunLock $root 'label'; try { ... } finally { Exit-TestRunLock $lock }
function Enter-TestRunLock([string]$Root, [string]$Label) {
  $path = Join-Path $Root '.cache/test-run.lock'
  New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
  if (Test-Path -LiteralPath $path) {
    $held = Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($held -and $held.pid -and (Get-Process -Id $held.pid -ErrorAction SilentlyContinue)) {
      throw ("Another test run is active in this tree (" + $held.label + ", pid " + $held.pid + ", since " + $held.at + "). Wait for it to finish; never run two pytest at once here.")
    }
    Remove-Item -LiteralPath $path -Force  # stale: its process is gone
  }
  [ordered]@{ pid = $PID; label = $Label; at = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding utf8
  return $path
}

function Exit-TestRunLock([string]$Path) {
  if ($Path -and (Test-Path -LiteralPath $Path)) {
    $held = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($held -and $held.pid -eq $PID) { Remove-Item -LiteralPath $Path -Force }
  }
}
