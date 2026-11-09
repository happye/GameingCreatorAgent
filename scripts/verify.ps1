# Tier 2 (milestone) gate: lock, format, lint, types, full pytest, CLI smoke.
# -Release adds the two reproducible offline wheel builds (tier 3). -SkipBuild is accepted for old callers.
# After a failed or interrupted full run, a new one needs a new `feat:` commit (next substantive
# batch) or -AllowRerun, which AGENTS.md Testing reserves for an explicit user instruction.
param([switch]$Release, [switch]$SkipBuild, [switch]$PreserveRuns, [switch]$AllowRerun)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Push-Location $repositoryRoot
$testRunRoot = $null
$passed = $false

# rmdir /s does not follow junctions, unlike Windows PowerShell 5.1 Remove-Item -Recurse.
# Folders locked by another Windows account (sandboxed runs) are skipped silently.
function Remove-RunDirectory([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return }
  cmd /c "rmdir /s /q `"$Path`" 2>nul" | Out-Null
}

$lastRunPath = Join-Path $repositoryRoot '.cache/verify-last.json'
function Write-LastRun([string]$Result) {
  $head = (git -C $repositoryRoot rev-parse HEAD).Trim()
  $record = [ordered]@{ result = $Result; head = $head; at = (Get-Date).ToString('o'); release = [bool]$Release }
  New-Item -ItemType Directory -Path (Split-Path $lastRunPath) -Force | Out-Null
  $record | ConvertTo-Json | Set-Content -LiteralPath $lastRunPath -Encoding utf8
}
if ((Test-Path -LiteralPath $lastRunPath) -and -not $AllowRerun) {
  $last = Get-Content -LiteralPath $lastRunPath -Raw -Encoding utf8 | ConvertFrom-Json
  if ($last.result -ne 'passed') {
    $features = @(git -C $repositoryRoot log --format=%s "$($last.head)..HEAD" | Where-Object { $_ -match '^feat' })
    if ($features.Count -eq 0) {
      Pop-Location
      throw ('Last full verify ' + $last.result + ' at ' + $last.at + ' (' + $last.head.Substring(0, 7) + ') and no feat: commit since. ' +
        'Repair with ./scripts/test-affected.ps1 or the failing node IDs (AGENTS.md Testing 3-4). ' +
        'A second full run in the same batch needs the user''s explicit instruction: -AllowRerun.')
    }
  }
}

try {
  Write-LastRun 'running'
  Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
  $pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
  $uvPath = Join-Path $repositoryRoot '.tools/uv/uv.exe'
  & $uvPath --no-config lock --check --offline --python $pythonPath --no-python-downloads
  if ($LASTEXITCODE -ne 0) { throw 'Dependency lock does not match the project.' }
  # Runs older than a day are leftovers of failed or interrupted runs.
  $runsRoot = Join-Path $repositoryRoot '.cache/pytest-runs'
  if (-not $PreserveRuns -and (Test-Path -LiteralPath $runsRoot)) {
    Get-ChildItem -LiteralPath $runsRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } |
      ForEach-Object { Remove-RunDirectory $_.FullName }
  }
  # Separate verification runs never reuse another Windows user's locked pytest directories.
  $testRunRoot = Join-Path $runsRoot ([guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $testRunRoot -Force | Out-Null
  # Avoid pytest's temporary cache-directory rename on Windows filesystem locks.
  New-Item -ItemType Directory -Path (Join-Path $testRunRoot 'cache') -Force | Out-Null
  $pytestArguments = @('-m', 'pytest', '-W', 'error', '--basetemp', (Join-Path $testRunRoot 'tmp'), '-o', ('cache_dir=' + (Join-Path $testRunRoot 'cache')))
  foreach ($arguments in @(@('-m', 'ruff', 'format', '--check', 'src', 'tests', 'scripts/validate-media.py', 'scripts/validate-storage.py', 'scripts/validate-inspection-ui.py', 'scripts/validate-temporal-gameplay.py', 'scripts/validate-visual-details.py', 'scripts/prepare-benchmark-review.py', 'scripts/prepare-benchmark-references.py', 'scripts/prepare-benchmark-plan.py', 'scripts/affected_tests.py', 'scripts/status.py'), @('-m', 'ruff', 'check', 'src', 'tests', 'scripts/validate-media.py', 'scripts/validate-storage.py', 'scripts/validate-inspection-ui.py', 'scripts/validate-temporal-gameplay.py', 'scripts/validate-visual-details.py', 'scripts/prepare-benchmark-review.py', 'scripts/prepare-benchmark-references.py', 'scripts/prepare-benchmark-plan.py', 'scripts/affected_tests.py', 'scripts/status.py'), @('-m', 'mypy'), $pytestArguments)) {
    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) { throw "Project check failed: $($arguments -join ' ')" }
  }
  if ($Release) {
    foreach ($buildNumber in @(1, 2)) {
      $outputDirectory = Join-Path $repositoryRoot ".cache/build/$buildNumber"
      & $uvPath --no-config build --wheel --no-build-isolation --offline --python $pythonPath --no-python-downloads --out-dir $outputDirectory
      if ($LASTEXITCODE -ne 0) { throw 'Offline wheel build failed.' }
    }
    $first = Join-Path $repositoryRoot '.cache/build/1/gamingcreator-0.1.0-py3-none-any.whl'
    $second = Join-Path $repositoryRoot '.cache/build/2/gamingcreator-0.1.0-py3-none-any.whl'
    $wheelHash = (Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash
    if ($wheelHash -ne (Get-FileHash -LiteralPath $second -Algorithm SHA256).Hash) { throw 'Repeated wheel builds differ.' }
    Write-Host "Repeated offline wheel builds match: $wheelHash"
  }
  & $pythonPath -m gamingcreator --help
  if ($LASTEXITCODE -ne 0) { throw 'CLI help failed.' }
  & (Join-Path $repositoryRoot '.venv/Scripts/gamingcreator.exe') --version
  if ($LASTEXITCODE -ne 0) { throw 'Installed console entry point failed.' }
  $passed = $true
  Write-Host 'All project checks passed. Media integration requires project-local FFmpeg; check pytest skip counts.'
} finally {
  Write-LastRun $(if ($passed) { 'passed' } else { 'failed' })
  # A passing run keeps nothing; a failing run keeps its temp files for diagnosis (pruned after a day).
  if ($testRunRoot -and $passed -and -not $PreserveRuns -and $env:GC_KEEP_TEST_MEDIA -ne '1') {
    Remove-RunDirectory $testRunRoot
  } elseif ($testRunRoot -and (Test-Path -LiteralPath $testRunRoot)) {
    Write-Host "Kept run files: $testRunRoot"
  }
  Pop-Location
}
