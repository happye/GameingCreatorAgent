[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourceBin)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain.ps1')
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$tools = Join-Path $root '.tools'
$destination = Join-Path $tools 'ffmpeg'
$source = [IO.Path]::GetFullPath($SourceBin)
$manifest = Get-ProjectMediaManifest $root
Assert-MediaPlainPath $tools
Assert-MediaPlainPath $destination
if (Test-Path -LiteralPath $destination) {
  Assert-ProjectMediaTools $root
  Write-Output 'Pinned media tools already prepared.'
  return
}
Assert-MediaBinaryDirectory $source $manifest
[IO.Directory]::CreateDirectory($tools) | Out-Null
$stage = Join-Path $tools ('.media-stage-' + [Guid]::NewGuid().ToString('N'))
$created = $false
$ownedFiles = @()
try {
  Assert-MediaPlainPath $stage
  if (Test-Path -LiteralPath $stage) { throw 'Media staging path already exists.' }
  [IO.Directory]::CreateDirectory($stage) | Out-Null
  $created = $true
  $bin = Join-Path $stage 'bin'
  [IO.Directory]::CreateDirectory($bin) | Out-Null
  foreach ($file in $manifest.files) {
    $from = Join-Path $source $file.path
    $to = Join-Path $bin $file.path
    Assert-MediaPlainPath $from
    Assert-MediaPlainPath $to
    $inputStream = [IO.File]::OpenRead($from)
    try {
      $outputStream = [IO.File]::Open($to, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
      $ownedFiles += $to
      try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
    } finally { $inputStream.Dispose() }
  }
  Assert-MediaBinaryDirectory $bin $manifest
  Assert-MediaPlainPath $stage
  Assert-MediaPlainPath $destination
  # Directory.Move never merges with or replaces an existing directory.
  [IO.Directory]::Move($stage, $destination)
  $created = $false
  Write-Output 'Pinned media tools prepared offline.'
} finally {
  if ($created) {
    try {
      $fullStage = [IO.Path]::GetFullPath($stage)
      $fullTools = [IO.Path]::GetFullPath($tools)
      if ([IO.Path]::GetDirectoryName($fullStage) -ne $fullTools -or [IO.Path]::GetFileName($fullStage) -notmatch '^\.media-stage-[a-f0-9]{32}$') { throw 'Unsafe media staging cleanup path.' }
      Assert-MediaPlainPath $fullStage
      foreach ($owned in $ownedFiles) {
        Assert-MediaPlainPath $owned
        [IO.File]::Delete($owned)
      }
      Assert-MediaPlainPath $bin
      [IO.Directory]::Delete($bin, $false)
      [IO.Directory]::Delete($fullStage, $false)
    } catch { Write-Warning ('Media staging cleanup deferred: ' + $_.Exception.Message) }
  }
}
