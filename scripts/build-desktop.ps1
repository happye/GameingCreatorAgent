param(
  [switch]$Smoke
)
# Builds desktop\bin\GamingCreator.exe with the C# compiler that ships with Windows
# (.NET Framework 4.x). Nothing is downloaded. -Smoke starts the workspace service through the
# built host, waits until it answers, and stops it again without opening a window.
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework C# compiler (csc.exe) is not available.' }
$source = Join-Path $repositoryRoot 'desktop\host\GamingCreatorHost.cs'
$output = Join-Path $repositoryRoot 'desktop\bin'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$exe = Join-Path $output 'GamingCreator.exe'
# The WebView2 SDK was downloaded once with the user's approval; every build re-checks its pinned hashes.
$pin = Get-Content -Raw -Encoding UTF8 (Join-Path $repositoryRoot 'docs/references/webview2-sdk.json') | ConvertFrom-Json
$sdk = Join-Path $repositoryRoot $pin.localDirectory
foreach ($property in $pin.files.PSObject.Properties) {
  $file = Join-Path $sdk $property.Name
  if (-not (Test-Path -LiteralPath $file)) { throw "Missing pinned WebView2 SDK file $($property.Name); see docs/references/webview2-sdk.json." }
  if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw "WebView2 SDK file $($property.Name) differs from its pinned SHA256." }
  if ($property.Name -like '*.dll') { Copy-Item -LiteralPath $file -Destination (Join-Path $output $property.Name) -Force }
}
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll "/reference:$(Join-Path $sdk 'Microsoft.Web.WebView2.Core.dll')" "/reference:$(Join-Path $sdk 'Microsoft.Web.WebView2.WinForms.dll')" "/out:$exe" $source
if ($LASTEXITCODE -ne 0) { throw "csc.exe failed with exit code $LASTEXITCODE." }
Write-Host "Built $exe"
if ($Smoke) {
  $info = New-Object System.Diagnostics.ProcessStartInfo $exe, '--smoke'
  $info.UseShellExecute = $false
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $process = [System.Diagnostics.Process]::Start($info)
  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  if (-not $process.WaitForExit(90000)) { $process.Kill(); throw 'Desktop host smoke test timed out.' }
  if ($process.ExitCode -ne 0 -or $stdout -notmatch 'READY http://127\.0\.0\.1:\d+/creation') {
    throw "Desktop host smoke test failed (exit $($process.ExitCode)): $stdout $stderr"
  }
  Write-Host $stdout.Trim()
}
