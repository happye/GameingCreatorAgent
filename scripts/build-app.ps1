param(
  [string]$Output = '',
  [switch]$Smoke,
  [long]$MaxBytes = 1610612736
)
# Assembles a self-contained portable app folder (default dist\GamingCreator, ignored by git):
# bundled Python, runtime packages without developer tools, the program installed as a normal
# package (no link back to this checkout), FFmpeg and the desktop EXE. Nothing is downloaded.
# The folder is refused if it would exceed -MaxBytes; -Smoke starts the service from the copy.
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Output) { $Output = Join-Path $repositoryRoot 'dist/GamingCreator' }
$marker = Join-Path $Output '.gamingcreator-app.json'
# Rebuilding replaces only the program parts; data a smoke run or a user left (.cache) stays.
$programParts = @('toolchain.json', 'scripts', '.tools', '.venv', 'desktop', '.gamingcreator-app.json')
function Remove-ProgramParts {
  foreach ($part in $programParts) {
    $path = Join-Path $Output $part
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue }
  }
}
$created = -not (Test-Path -LiteralPath $Output)
if (-not $created) {
  if (-not (Test-Path -LiteralPath $marker)) { throw "$Output exists and was not created by this script; nothing was changed." }
  Remove-ProgramParts
}
New-Item -ItemType Directory -Force -Path $Output | Out-Null
function Copy-Tree([string]$From, [string]$To, [string[]]$ExcludeDirectories = @()) {
  $arguments = @($From, $To, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
  if ($ExcludeDirectories.Count) { $arguments += '/XD'; $arguments += $ExcludeDirectories }
  & robocopy @arguments | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Copy failed: $From (robocopy $LASTEXITCODE)" }
}
try {
  & (Join-Path $PSScriptRoot 'build-desktop.ps1')
  Copy-Item -LiteralPath (Join-Path $repositoryRoot 'toolchain.json') -Destination $Output
  Copy-Tree (Join-Path $repositoryRoot 'scripts') (Join-Path $Output 'scripts') @('__pycache__')
  Copy-Tree (Join-Path $repositoryRoot '.tools/python') (Join-Path $Output '.tools/python') @('__pycache__')
  Copy-Tree (Join-Path $repositoryRoot '.tools/ffmpeg/bin') (Join-Path $Output '.tools/ffmpeg/bin')
  Copy-Tree (Join-Path $repositoryRoot 'desktop/bin') (Join-Path $Output 'desktop/bin')
  $developerOnly = @('__pycache__', 'mypy', 'mypyc', '_pytest', 'pytest', 'ruff', 'hatchling', 'iniconfig', 'pluggy', 'pathspec', 'trove_classifiers')
  $venv = Join-Path $Output '.venv'
  Copy-Tree (Join-Path $repositoryRoot '.venv') $venv $developerOnly
  $site = Join-Path $venv 'Lib/site-packages'
  Get-ChildItem -LiteralPath $site -Force | Where-Object {
    $_.Name -match '^(mypy|pytest|ruff|hatchling|iniconfig|pluggy|pathspec|trove_classifiers)[-_].*dist-info$' -or
    $_.Name -match '^_editable_impl_gamingcreator' -or $_.Name -like 'gamingcreator-*.dist-info' -or
    $_.Name -like '*__mypyc*'
  } | Remove-Item -Recurse -Force
  Copy-Tree (Join-Path $repositoryRoot 'src/gamingcreator') (Join-Path $site 'gamingcreator') @('__pycache__')
  # The venv launcher finds its interpreter through pyvenv.cfg; point it at the bundled copy.
  $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $repositoryRoot 'toolchain.json') | ConvertFrom-Json
  $runtime = Join-Path $Output ('.tools/python/' + $manifest.python.request)
  $config = Join-Path $venv 'pyvenv.cfg'
  $lines = Get-Content -Encoding UTF8 $config | ForEach-Object {
    if ($_ -match '^home\s*=') { "home = $runtime" }
    elseif ($_ -match '^(executable|command)\s*=') { $null }
    else { $_ }
  }
  # No byte-order mark: the venv launcher parses this file itself.
  [IO.File]::WriteAllLines($config, [string[]]@($lines | Where-Object { $null -ne $_ }), (New-Object System.Text.UTF8Encoding $false))
  $bytes = ($programParts | Where-Object { Test-Path -LiteralPath (Join-Path $Output $_) } |
    ForEach-Object { Get-ChildItem -LiteralPath (Join-Path $Output $_) -Recurse -File -Force } | Measure-Object Length -Sum).Sum
  if ($bytes -gt $MaxBytes) { throw "App folder is $bytes bytes, above the $MaxBytes limit." }
  $version = (Select-String -LiteralPath (Join-Path $repositoryRoot 'pyproject.toml') -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
  $commit = (& git -C $repositoryRoot rev-parse HEAD 2>$null)
  @{ schemaVersion = 'gamingcreator-app-v1'; builtAt = (Get-Date).ToUniversalTime().ToString('o'); bytes = $bytes; version = $version; commit = "$commit".Trim() } |
    ConvertTo-Json | Set-Content -Encoding UTF8 -Path $marker
  Write-Host ("Built {0} ({1:N0} MB)" -f $Output, ($bytes / 1MB))
} catch {
  if ($created) { Remove-Item -LiteralPath $Output -Recurse -Force -ErrorAction SilentlyContinue } else { Remove-ProgramParts }
  throw
}
if ($Smoke) {
  $exe = Join-Path $Output 'desktop/bin/GamingCreator.exe'
  $info = New-Object System.Diagnostics.ProcessStartInfo $exe, '--smoke'
  $info.UseShellExecute = $false
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $info.EnvironmentVariables.Remove('PYTHONPATH')
  $process = [System.Diagnostics.Process]::Start($info)
  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Packaged app smoke test timed out.' }
  if ($process.ExitCode -ne 0 -or $stdout -notmatch 'READY http://127\.0\.0\.1:\d+/creation') {
    throw "Packaged app smoke test failed (exit $($process.ExitCode)): $stdout $stderr"
  }
  Write-Host ("Smoke " + $stdout.Trim())
}
