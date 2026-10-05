param(
  [string]$Video,
  [string]$Run,
  [string]$Project = 'artifacts/demo-phase0',
  [string]$Config = 'config.example.json',
  [string]$Query = '寻找角色打斗和攻击的片段',
  [ValidateSet('lexical', 'semantic', 'hybrid')][string]$Mode = 'hybrid',
  [ValidateRange(1, 100)][int]$TopK = 10,
  [string]$MaxCostCny = '5'
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
$previousOutputEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup-demo.ps1 first.' }
if (([bool]$Video) -eq ([bool]$Run)) { throw 'Provide either -Video for a new analysis or -Run for an existing completed run.' }
Push-Location $repositoryRoot
try {
  if ($Video) {
    $analysis = & $pythonPath -m gamingcreator analyze $Video --project $Project --config $Config --max-cost-cny $MaxCostCny
    if ($LASTEXITCODE -ne 0) { throw 'Analysis stopped; its diagnostic contains the run ID and completed windows remain saved.' }
    $Run = ($analysis | ConvertFrom-Json).runId
  }
  $search = & $pythonPath -m gamingcreator search $Query --project $Project --run $Run --mode $Mode --top-k $TopK
  if ($LASTEXITCODE -ne 0) { throw 'Search did not complete; inspect the CLI diagnostic.' }
  $result = $search | ConvertFrom-Json
  Write-Output ("Run: $Run; mode: $Mode; candidates: " + $result.candidates.Count)
  $result.candidates | Select-Object rank,startTimecode,endTimecode,@{Name='facts';Expression={if ($_.displayFacts) { $_.displayFacts -join '；' } else { $_.observableFacts -join '；' }}},@{Name='待核对';Expression={if ($_.displayUncertainty) { $_.displayUncertainty } else { $_.uncertainty }}} | Format-List
  Write-Output ("Timeline: " + (Join-Path $Project "runs/$Run/semantic_timeline.json"))
  Write-Output ("Search record: " + $result.retrievalId + '; JSON files are saved under runs/<run>/searches/.')
  Write-Output 'These are model observations and candidate intervals. Human Top-10 quality remains unverified.'
} finally {
  [Console]::OutputEncoding = $previousOutputEncoding
  Pop-Location
}
