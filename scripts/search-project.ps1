param(
  [Parameter(Mandatory = $true)][string]$Project,
  [Parameter(Mandatory = $true)][string[]]$Run,
  [Parameter(Mandatory = $true)][string]$Query,
  [ValidateSet('lexical', 'semantic', 'hybrid')][string]$Mode = 'hybrid',
  [ValidateRange(1, 100)][int]$TopK = 10,
  [double]$MinSimilarity = 0.80,
  [ValidateSet('v1', 'v2', 'v3', 'v4')][string]$DetailProfile,
  [switch]$Json
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$projectSearchArguments = @('-B', '-m', 'gamingcreator', 'search-project', $Query, '--project', $Project, '--mode', $Mode, '--top-k', $TopK, '--min-similarity', $MinSimilarity.ToString([Globalization.CultureInfo]::InvariantCulture))
foreach ($projectSearchRun in $Run) { $projectSearchArguments += @('--run', $projectSearchRun) }
if ($DetailProfile) { $projectSearchArguments += @('--detail-profile', $DetailProfile) }
$projectSearchOutputEncoding = $OutputEncoding
$projectSearchConsoleEncoding = [Console]::OutputEncoding
$projectSearchExit = 1
Push-Location $repositoryRoot
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  $projectSearchOutput = & (Join-Path $repositoryRoot '.venv/Scripts/python.exe') @projectSearchArguments
  $projectSearchExit = $LASTEXITCODE
  if ($projectSearchExit -eq 0) {
    if ($Json) { Write-Output $projectSearchOutput }
    else {
      $projectSearchResult = $projectSearchOutput | ConvertFrom-Json
      Write-Output ("已检查录像：" + $projectSearchResult.sources.Count + "；候选：" + $projectSearchResult.candidates.Count)
      $projectSearchResult.candidates | Select-Object rank,sourceName,startTimecode,endTimecode,@{Name='画面描述';Expression={$_.displayFacts -join '；'}},@{Name='待核对';Expression={$_.displayUncertainty}} | Format-List
      Write-Output ("本次查询记录：" + $projectSearchResult.recordPath)
      Write-Output '结果是待核对候选；检索分数不表示准确率。'
    }
  }
} finally {
  Pop-Location
  $OutputEncoding = $projectSearchOutputEncoding
  [Console]::OutputEncoding = $projectSearchConsoleEncoding
}
exit $projectSearchExit
