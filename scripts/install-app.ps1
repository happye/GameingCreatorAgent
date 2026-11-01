param(
  [string]$Source = '',
  [string]$Destination = '',
  [switch]$Uninstall,
  [switch]$Smoke
)
# Installs, upgrades or uninstalls the portable app built by build-app.ps1, per user, with no
# registry, shortcut or system change. Only the program parts are replaced or removed; the
# user's data in the same folder (.cache with creations, ledgers and logs, projects, outputs)
# is never touched. An upgrade stages the new copy next to the old one and swaps it in,
# restoring the previous program parts if any step fails.
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Source) { $Source = Join-Path $repositoryRoot 'dist/GamingCreator' }
if (-not $Destination) { $Destination = Join-Path $env:LOCALAPPDATA 'Programs/GamingCreator' }
# Relative paths mean the PowerShell location, not the process directory.
function Resolve-UserPath([string]$Path) {
  [IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path))
}
$Source = Resolve-UserPath $Source
$Destination = Resolve-UserPath $Destination
$programParts = @('toolchain.json', 'scripts', '.tools', '.venv', 'desktop', 'docs', 'models', 'licenses', '.gamingcreator-app.json')
$marker = '.gamingcreator-app.json'
$receiptName = '.gamingcreator-install.json'
# Left by an uninstall that kept user data, so the same folder can be installed into again.
$dataMarker = '.gamingcreator-data.json'

function Read-Marker([string]$Folder) {
  $path = Join-Path $Folder $marker
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  $value = Get-Content -Raw -Encoding UTF8 -LiteralPath $path | ConvertFrom-Json
  if ($value.schemaVersion -ne 'gamingcreator-app-v1') { throw "$path is not a Gaming Creator app marker." }
  return $value
}

function Assert-NotRunning([string]$Folder) {
  $prefix = $Folder.TrimEnd('\') + '\'
  $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $path = $null
    try { $path = $_.Path } catch { }
    $path -and $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
  })
  if ($running.Count) {
    throw "The app in $Folder is running ($(($running | ForEach-Object Name) -join ', ')); close it first. Nothing was changed."
  }
}

# A plain rename on one volume: it either fully happens or not at all (Move-Item can fall back
# to a partial copy when a file inside is in use).
function Move-Entry([string]$From, [string]$To) {
  if (Test-Path -LiteralPath $From -PathType Container) { [IO.Directory]::Move($From, $To) } else { [IO.File]::Move($From, $To) }
}

function User-Entries([string]$Folder) {
  @(Get-ChildItem -LiteralPath $Folder -Force | Where-Object { $programParts -notcontains $_.Name -and $_.Name -notin @($receiptName, $dataMarker) } |
    ForEach-Object Name)
}

$installed = $null
if (Test-Path -LiteralPath $Destination) {
  $installed = Read-Marker $Destination
  $keptData = Test-Path -LiteralPath (Join-Path $Destination $dataMarker)
  if (-not $installed -and -not $keptData -and @(Get-ChildItem -LiteralPath $Destination -Force).Count) {
    throw "$Destination is not empty and holds no Gaming Creator app; nothing was changed."
  }
}

if ($Uninstall) {
  if (-not $installed) { throw "No Gaming Creator app is installed in $Destination." }
  Assert-NotRunning $Destination
  # Rename every program part aside first, so a file in use stops the uninstall cleanly.
  $trash = Join-Path (Split-Path -Parent $Destination) ((Split-Path -Leaf $Destination) + '.uninstall-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
  New-Item -ItemType Directory -Path $trash | Out-Null
  $aside = New-Object System.Collections.Generic.List[string]
  try {
    foreach ($part in $programParts + $receiptName) {
      $path = Join-Path $Destination $part
      if (Test-Path -LiteralPath $path) { Move-Entry $path (Join-Path $trash $part); $aside.Add($part) }
    }
  } catch {
    foreach ($part in $aside) { Move-Entry (Join-Path $trash $part) (Join-Path $Destination $part) }
    Remove-Item -LiteralPath $trash -Recurse -Force
    throw
  }
  Remove-Item -LiteralPath $trash -Recurse -Force
  $kept = User-Entries $Destination
  if ($kept.Count) {
    $note = [ordered]@{ schemaVersion = 'gamingcreator-data-v1'; uninstalledAt = (Get-Date).ToUniversalTime().ToString('o'); kept = $kept }
    [IO.File]::WriteAllText((Join-Path $Destination $dataMarker), ($note | ConvertTo-Json), (New-Object System.Text.UTF8Encoding $false))
    Write-Host ("Uninstalled the program from {0}; your data was kept: {1}. Installing here again reuses it; delete the folder yourself when you no longer need it." -f $Destination, ($kept -join ', '))
  } else {
    Remove-Item -LiteralPath (Join-Path $Destination $dataMarker) -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Destination -Force
    Write-Host "Uninstalled the program; $Destination held no data and was removed."
  }
  return
}

$built = Read-Marker $Source
if (-not $built) { throw "$Source is not an app folder built by build-app.ps1 (no marker)." }
if ($built.incomplete) { throw "$Source is an unfinished build; run build-app.ps1 again first." }
foreach ($part in $programParts) {
  if (-not (Test-Path -LiteralPath (Join-Path $Source $part))) { throw "$Source is incomplete: $part is missing." }
}
if ($Source.TrimEnd('\') -eq $Destination.TrimEnd('\')) { throw 'Source and destination are the same folder.' }
if ($installed) { Assert-NotRunning $Destination }
$parent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$needed = [long]$built.bytes + 256MB
$drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($Destination))
if ($drive.AvailableFreeSpace -lt $needed) {
  throw ("Not enough free space on {0}: {1:N0} MB needed, {2:N0} MB free. Nothing was changed." -f $drive.Name, ($needed / 1MB), ($drive.AvailableFreeSpace / 1MB))
}

$token = [guid]::NewGuid().ToString('N').Substring(0, 8)
$leaf = Split-Path -Leaf $Destination
$staging = Join-Path $parent ($leaf + '.install-' + $token)
$previous = Join-Path $parent ($leaf + '.previous-' + $token)
$created = -not (Test-Path -LiteralPath $Destination)
$moved = New-Object System.Collections.Generic.List[string]
$placed = New-Object System.Collections.Generic.List[string]
$succeeded = $false
try {
  # Stage on the same volume so the swap below is a set of quick renames.
  New-Item -ItemType Directory -Path $staging | Out-Null
  foreach ($part in $programParts) {
    $from = Join-Path $Source $part
    if (Test-Path -LiteralPath $from -PathType Container) {
      & robocopy $from (Join-Path $staging $part) /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD __pycache__ | Out-Null
      if ($LASTEXITCODE -ge 8) { throw "Copy failed: $part (robocopy $LASTEXITCODE)" }
    } else {
      Copy-Item -LiteralPath $from -Destination (Join-Path $staging $part)
    }
  }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  New-Item -ItemType Directory -Path $previous | Out-Null
  foreach ($part in $programParts) {
    $current = Join-Path $Destination $part
    if (Test-Path -LiteralPath $current) {
      Move-Entry $current (Join-Path $previous $part)
      $moved.Add($part)
    }
    Move-Entry (Join-Path $staging $part) $current
    $placed.Add($part)
  }
  $receipt = [ordered]@{
    schemaVersion = 'gamingcreator-install-v1'
    installedAt = (Get-Date).ToUniversalTime().ToString('o')
    source = $Source
    builtAt = $built.builtAt
    version = $built.version
    commit = $built.commit
    upgradedFrom = if ($installed) { [ordered]@{ builtAt = $installed.builtAt; version = $installed.version; commit = $installed.commit } } else { $null }
  }
  [IO.File]::WriteAllText((Join-Path $Destination $receiptName), ($receipt | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding $false))
  Remove-Item -LiteralPath (Join-Path $Destination $dataMarker) -Force -ErrorAction SilentlyContinue
  
  # After the swap, point the venv at this destination's bundled interpreter (not the build folder).
  $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $Destination 'toolchain.json') | ConvertFrom-Json
  $runtime = Join-Path $Destination ('.tools/python/' + $manifest.python.request)
  if (-not (Test-Path -LiteralPath $runtime)) { throw "Installed runtime missing at $runtime" }
  $config = Join-Path $Destination '.venv/pyvenv.cfg'
  $lines = Get-Content -Encoding UTF8 $config | ForEach-Object {
    if ($_ -match '^home\s*=') { "home = $runtime" }
    elseif ($_ -match '^(executable|command)\s*=') { $null }
    else { $_ }
  }
  [IO.File]::WriteAllLines($config, [string[]]@($lines | Where-Object { $null -ne $_ }), (New-Object System.Text.UTF8Encoding $false))

  $succeeded = $true
} catch {
  # Put the previous program back exactly as it was; the user's data was never moved.
  foreach ($part in $placed) { Remove-Item -LiteralPath (Join-Path $Destination $part) -Recurse -Force -ErrorAction SilentlyContinue }
  foreach ($part in $moved) {
    try { Move-Entry (Join-Path $previous $part) (Join-Path $Destination $part) } catch { Write-Warning "Could not restore $part; it is kept in $previous." }
  }
  if ($created) { Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue }
  throw
} finally {
  if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue }
  # After a failed rollback the old program stays in the .previous folder rather than being lost.
  $empty = (Test-Path -LiteralPath $previous) -and -not @(Get-ChildItem -LiteralPath $previous -Force).Count
  if ($succeeded -or $empty) { Remove-Item -LiteralPath $previous -Recurse -Force -ErrorAction SilentlyContinue }
}
$verb = if ($installed) { 'Upgraded' } else { 'Installed' }
Write-Host ("{0} Gaming Creator in {1}. Start it with {2}" -f $verb, $Destination, (Join-Path $Destination 'desktop\bin\GamingCreator.exe'))
if ($Smoke) {
  $info = New-Object System.Diagnostics.ProcessStartInfo (Join-Path $Destination 'desktop/bin/GamingCreator.exe'), '--smoke'
  $info.UseShellExecute = $false
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $info.EnvironmentVariables.Remove('PYTHONPATH')
  $process = [System.Diagnostics.Process]::Start($info)
  # Read both pipes concurrently so a full stderr pipe or a hung app cannot block the timeout.
  $outTask = $process.StandardOutput.ReadToEndAsync()
  $errTask = $process.StandardError.ReadToEndAsync()
  if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Installed app smoke test timed out.' }
  $stdout = $outTask.Result
  $stderr = $errTask.Result
  if ($process.ExitCode -ne 0 -or $stdout -notmatch 'READY http://127\.0\.0\.1:\d+/creation') {
    throw "Installed app smoke test failed (exit $($process.ExitCode)): $stdout $stderr"
  }
  Write-Host ("Smoke " + $stdout.Trim())
}
