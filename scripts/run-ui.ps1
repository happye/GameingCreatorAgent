param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup-demo.ps1 first.' }
Push-Location $repositoryRoot
try {
  Write-Host "Open http://127.0.0.1:$Port/ after the server prints Inspection UI."
  & $pythonPath -B -m gamingcreator.ui --host 127.0.0.1 --port $Port --repository $repositoryRoot
  if ($LASTEXITCODE -ne 0) { throw 'The inspection page stopped.' }
} finally { Pop-Location }
