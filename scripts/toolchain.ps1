# Shared project-local toolchain checks; dot-source from init/setup/verify.
function Assert-ProjectToolchain {
  param([string]$RepositoryRoot, [switch]$RequireVenv)
  if (-not [Environment]::Is64BitOperatingSystem -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'The pinned toolchain requires Windows x64.' }
  $manifest = Get-Content (Join-Path $RepositoryRoot 'toolchain.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  $receiptPath = Join-Path $RepositoryRoot '.tools/toolchain-receipt.json'
  if (-not (Test-Path -LiteralPath $receiptPath)) { throw 'Run scripts/setup-env.ps1 to prepare the verified toolchain.' }
  $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($receipt.uvArchiveSha256 -ne $manifest.uv.sha256 -or
      $receipt.pythonArchiveSha256 -ne $manifest.python.sha256 -or
      $receipt.pythonBuild -ne $manifest.python.build) { throw 'Installed toolchain provenance differs from toolchain.json.' }
  $uvPath = Join-Path $RepositoryRoot '.tools/uv/uv.exe'
  if ((Get-FileHash -LiteralPath $uvPath -Algorithm SHA256).Hash -ne $receipt.uvExeSha256) { throw 'Project uv executable hash differs from the installation receipt.' }
  $versionText = (& $uvPath --version) -join "`n"
  if ($LASTEXITCODE -ne 0 -or $versionText -notmatch ('^uv ' + [regex]::Escape($manifest.uv.version) + '\b')) { throw 'Project uv version differs from toolchain.json.' }
  $runtimeRoot = Join-Path $RepositoryRoot ('.tools/python/' + $manifest.python.request)
  foreach ($file in $receipt.pythonFiles) {
    $filePath = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $file.path))
    if (-not $filePath.StartsWith($runtimeRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid runtime receipt path.' }
    if ((Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash -ne $file.sha256) { throw 'Project Python runtime hash differs from the installation receipt.' }
  }
  if (@($receipt.pythonFiles).Count -eq 0) { throw 'Runtime receipt has no verified files.' }
  $pythonPath = Join-Path $runtimeRoot 'python.exe'
  if ($RequireVenv) { $pythonPath = Join-Path $RepositoryRoot '.venv/Scripts/python.exe' }
  $probe = @'
import pathlib, struct, sys, sysconfig
root, runtime, version, require_venv = sys.argv[1:]
root, runtime = pathlib.Path(root).resolve(), pathlib.Path(runtime).resolve()
assert sys.implementation.name == 'cpython' and sys.version_info[:3] == tuple(map(int, version.split('.')))
assert struct.calcsize('P') == 8 and not sysconfig.get_config_var('Py_GIL_DISABLED')
assert pathlib.Path(sys.base_prefix).resolve() == runtime
if require_venv == 'yes':
    assert pathlib.Path(sys.prefix).resolve() == root / '.venv'
    cfg = (root / '.venv' / 'pyvenv.cfg').read_text().lower()
    assert 'include-system-site-packages = false' in cfg
'@
  & $pythonPath -I -B -c $probe $RepositoryRoot $runtimeRoot $manifest.python.version $(if ($RequireVenv) { 'yes' } else { 'no' })
  if ($LASTEXITCODE -ne 0) { throw 'Project Python version, ABI or environment boundary is invalid.' }
}

function Assert-MediaPlainPath {
  param([string]$Path)
  $candidate = [IO.Path]::GetFullPath($Path)
  while ($candidate) {
    $item = Get-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
    if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Media paths must not contain reparse points.' }
    $parent = [IO.Path]::GetDirectoryName($candidate)
    if ($parent -eq $candidate) { break }
    $candidate = $parent
  }
}

function Get-ProjectMediaManifest {
  param([string]$RepositoryRoot)
  $manifestPath = Join-Path $RepositoryRoot 'docs/references/media-toolchain.json'
  Assert-MediaPlainPath $manifestPath
  $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($manifest.schemaVersion -ne 1 -or @($manifest.files).Count -ne 9) { throw 'Invalid media toolchain manifest.' }
  $names = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
  foreach ($file in $manifest.files) {
    if ($file.path -isnot [string] -or $file.path -notmatch '^[a-zA-Z0-9_-]+\.(exe|dll)$' -or
        $file.sha256 -isnot [string] -or $file.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
        -not $names.Add($file.path)) { throw 'Invalid media toolchain path, duplicate or SHA256.' }
  }
  return $manifest
}

function Assert-MediaBinaryDirectory {
  param([string]$BinaryRoot, $Manifest)
  $binaryRoot = [IO.Path]::GetFullPath($BinaryRoot)
  Assert-MediaPlainPath $binaryRoot
  foreach ($file in $Manifest.files) {
    $filePath = Join-Path $binaryRoot $file.path
    Assert-MediaPlainPath $filePath
    if ((Get-FileHash -LiteralPath $filePath -Algorithm SHA256 -ErrorAction Stop).Hash -ne $file.sha256) { throw 'Project FFmpeg binary/DLL differs from the pinned media toolchain.' }
  }
}

function Assert-ProjectMediaTools {
  param([string]$RepositoryRoot)
  $manifest = Get-ProjectMediaManifest $RepositoryRoot
  Assert-MediaBinaryDirectory (Join-Path $RepositoryRoot '.tools/ffmpeg/bin') $manifest
}
