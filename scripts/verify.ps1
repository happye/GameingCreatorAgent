param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Push-Location $repositoryRoot
try {
  Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
  $pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
  $uvPath = Join-Path $repositoryRoot '.tools/uv/uv.exe'
  & $uvPath --no-config lock --check --offline --python $pythonPath --no-python-downloads
  if ($LASTEXITCODE -ne 0) { throw 'Dependency lock does not match the project.' }
  # Separate verification runs never reuse another Windows user's locked pytest directories.
  $testRunRoot = Join-Path $repositoryRoot ('.cache/pytest-runs/' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $testRunRoot -Force | Out-Null
  # Avoid pytest's temporary cache-directory rename on Windows filesystem locks.
  New-Item -ItemType Directory -Path (Join-Path $testRunRoot 'cache') -Force | Out-Null
  $pytestArguments = @('-m', 'pytest', '-W', 'error', '--basetemp', (Join-Path $testRunRoot 'tmp'), '-o', ('cache_dir=' + (Join-Path $testRunRoot 'cache')))
  foreach ($arguments in @(@('-m', 'ruff', 'format', '--check', 'src', 'tests', 'scripts/validate-media.py', 'scripts/validate-storage.py', 'scripts/validate-inspection-ui.py', 'scripts/validate-temporal-gameplay.py', 'scripts/validate-visual-details.py', 'scripts/prepare-benchmark-review.py', 'scripts/prepare-benchmark-references.py', 'scripts/prepare-benchmark-plan.py'), @('-m', 'ruff', 'check', 'src', 'tests', 'scripts/validate-media.py', 'scripts/validate-storage.py', 'scripts/validate-inspection-ui.py', 'scripts/validate-temporal-gameplay.py', 'scripts/validate-visual-details.py', 'scripts/prepare-benchmark-review.py', 'scripts/prepare-benchmark-references.py', 'scripts/prepare-benchmark-plan.py'), @('-m', 'mypy'), $pytestArguments)) {
    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) { throw "Project check failed: $($arguments -join ' ')" }
  }
  if (-not $SkipBuild) {
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
  Write-Host 'All project checks passed. Media integration requires project-local FFmpeg; check pytest skip counts.'
} finally { Pop-Location }
