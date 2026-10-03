$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$testDirectory = Join-Path $repositoryRoot ('artifacts/metric-tests/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDirectory -Force | Out-Null
$references = @(1..10 | ForEach-Object { "event-$_" })
$sevenGood = @(1..7 | ForEach-Object { @{eventId="event-$_"; grade=2} })
$duplicateHits = $sevenGood + @(@{eventId='event-1';grade=3},@{eventId='event-1';grade=3},@{eventId='event-2';grade=3})
$fixture = @{schemaVersion=1;evidenceType='synthetic_metric_test';datasetId='metric-regression-v1';queries=@(
    @{id='seven';kind='main';referenceEventIds=$references;hits=$duplicateHits},
    @{id='one';kind='main';referenceEventIds=$references;hits=@(@{eventId='event-1';grade=3})},
    @{id='negative';kind='negative';referenceEventIds=@();hits=@(@{eventId='irrelevant-1';grade=0})}
)}
$inputPath = Join-Path $testDirectory 'input.json'
$fixture | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $inputPath -Encoding utf8
$report = (& (Join-Path $PSScriptRoot 'score-retrieval.ps1') -InputPath $inputPath) | ConvertFrom-Json
if ($report.queries[0].usefulRateAt10 -ne 0.7 -or $report.queries[0].duplicateSlots -ne 3 -or -not $report.queries[0].mainMetricPassed) { throw 'Fixed denominator or event deduplication regression.' }
if ($report.queries[1].usefulRateAt10 -ne 0.1 -or $report.queries[1].mainMetricPassed) { throw 'Short-return inflation regression.' }
if (-not $report.queries[2].negativeReturnedAny -or $report.phase0QualityVerified) { throw 'Negative query or synthetic verification regression.' }
foreach ($invalidGrade in @($null, $true, '2', 2.5, 4, -1)) {
    $fixture.queries[1].hits[0].grade = $invalidGrade
    $fixture | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $inputPath -Encoding utf8
    $rejected = $false
    try { & (Join-Path $PSScriptRoot 'score-retrieval.ps1') -InputPath $inputPath | Out-Null } catch { $rejected = $_.Exception.Message -eq 'Every hit needs an eventId and a judged integer grade.' }
    if (-not $rejected) { throw 'Invalid or unjudged grade was not rejected.' }
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $testDirectory 'result.json') -Encoding utf8
Write-Host "Metric regression passed: $testDirectory/result.json"
