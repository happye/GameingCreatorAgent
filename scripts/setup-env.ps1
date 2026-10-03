param([switch]$Offline, [switch]$CreateLock)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
Push-Location $repositoryRoot
try {
  if (-not [Environment]::Is64BitOperatingSystem -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') {
    throw 'The pinned toolchain requires Windows x64.'
  }
  $manifest = Get-Content 'toolchain.json' -Raw -Encoding UTF8 | ConvertFrom-Json
  $downloadRoot = Join-Path $repositoryRoot '.cache/uv/downloads'
  New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null

  function Get-VerifiedArchive {
    param($Spec, [string]$Name)
    $archivePath = Join-Path $downloadRoot $Name
    if (-not (Test-Path -LiteralPath $archivePath)) {
      if ($Offline) { throw "Verified offline archive is missing: $Name" }
      $partialPath = $archivePath + '.partial'
      # Official GitHub asset API bypasses release-page redirects; content is hash-pinned.
      & curl.exe --fail --location --http1.1 --connect-timeout 30 --max-time 1800 --retry 2 --retry-all-errors --continue-at - --header 'Accept: application/octet-stream' --header 'User-Agent: GamingCreatorAgent-bootstrap' --output $partialPath $Spec.downloadUrl
      if ($LASTEXITCODE -ne 0) { throw "Archive download failed: $Name; the project-local partial file can be resumed." }
      if ((Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash -ne $Spec.sha256) { throw "Archive SHA256 mismatch: $Name; no downloaded executable was run." }
      Move-Item -LiteralPath $partialPath -Destination $archivePath
    }
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $Spec.sha256) { throw "Cached archive SHA256 mismatch: $Name" }
    return $archivePath
  }

  $receiptPath = Join-Path $repositoryRoot '.tools/toolchain-receipt.json'
  if (-not (Test-Path -LiteralPath $receiptPath)) {
    $uvArchive = Get-VerifiedArchive $manifest.uv ('uv-' + $manifest.uv.version + '-windows-x64.zip')
    $pythonArchive = Get-VerifiedArchive $manifest.python ('cpython-' + $manifest.python.version + '-' + $manifest.python.build + '-windows-x64.tar.gz')
    $stageRoot = Join-Path $repositoryRoot ('.tools/bootstrap-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    Expand-Archive -LiteralPath $uvArchive -DestinationPath (Join-Path $stageRoot 'uv')
    & tar.exe -xf $pythonArchive -C $stageRoot
    if ($LASTEXITCODE -ne 0) { throw 'Portable Python archive extraction failed.' }
    $uvSource = @(Get-ChildItem (Join-Path $stageRoot 'uv') -Filter uv.exe -Recurse -File)
    if ($uvSource.Count -ne 1 -or -not (Test-Path (Join-Path $stageRoot 'python/python.exe'))) { throw 'Unexpected official archive layout.' }
    $uvDirectory = Join-Path $repositoryRoot '.tools/uv'
    $runtimeRoot = Join-Path $repositoryRoot ('.tools/python/' + $manifest.python.request)
    if (Test-Path -LiteralPath $runtimeRoot) { throw 'Runtime directory exists without a receipt. Inspect it before reinitializing.' }
    New-Item -ItemType Directory -Path $uvDirectory, (Split-Path $runtimeRoot) -Force | Out-Null
    Copy-Item -LiteralPath $uvSource[0].FullName -Destination (Join-Path $uvDirectory 'uv.exe') -Force
    Move-Item -LiteralPath (Join-Path $stageRoot 'python') -Destination $runtimeRoot
    $fileHashes = @(Get-ChildItem -LiteralPath $runtimeRoot -File -Recurse | ForEach-Object {
      @{ path = $_.FullName.Substring($runtimeRoot.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    @{
      schemaVersion = 1
      uvArchiveSha256 = $manifest.uv.sha256
      uvExeSha256 = (Get-FileHash (Join-Path $uvDirectory 'uv.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
      pythonArchiveSha256 = $manifest.python.sha256
      pythonBuild = $manifest.python.build
      pythonFiles = $fileHashes
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
  }
  Assert-ProjectToolchain -RepositoryRoot $repositoryRoot
  $uvPath = Join-Path $repositoryRoot '.tools/uv/uv.exe'
  $pythonPath = Join-Path $repositoryRoot ('.tools/python/' + $manifest.python.request + '/python.exe')
  if (-not (Test-Path '.venv/Scripts/python.exe')) {
    & $pythonPath -I -B -m venv --without-pip (Join-Path $repositoryRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Project virtual environment creation failed.' }
  }
  Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv
  $offlineArguments = @()
  if ($Offline) { $offlineArguments = @('--offline') }
  if ($CreateLock) {
    & $uvPath --no-config lock --python $pythonPath --no-python-downloads --default-index https://pypi.org/simple @offlineArguments
    if ($LASTEXITCODE -ne 0) { throw 'Dependency lock creation failed.' }
  } elseif (-not (Test-Path 'uv.lock')) { throw 'uv.lock is missing. Only the dependency owner should create it with -CreateLock.' }
  & $uvPath --no-config sync --locked --python $pythonPath --no-python-downloads --default-index https://pypi.org/simple @offlineArguments
  if ($LASTEXITCODE -ne 0) { throw 'Locked project package synchronization failed.' }
  Write-Host 'Pinned tools and packages are ready inside this repository.'
} finally { Pop-Location }
