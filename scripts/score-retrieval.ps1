param([Parameter(Mandatory)][string]$InputPath)
$ErrorActionPreference = 'Stop'
$benchmark = Get-Content -LiteralPath $InputPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($benchmark.schemaVersion -ne 1 -or @($benchmark.queries).Count -eq 0) { throw 'Invalid benchmark schema.' }
$results = @()
$queryIds = @()
foreach ($query in $benchmark.queries) {
    if (-not $query.id -or $query.id -in $queryIds) { throw 'Missing or duplicate query ID.' }
    $queryIds += $query.id
    $references = @($query.referenceEventIds)
    if (@($references | Select-Object -Unique).Count -ne $references.Count) { throw 'Duplicate reference events.' }
    if ($query.kind -notin @('main','sparse','negative')) { throw 'Unknown query group.' }
    if ($query.kind -eq 'main' -and $references.Count -lt 10) { throw 'Main queries need ten independent reference events.' }
    if ($query.kind -eq 'sparse' -and ($references.Count -lt 1 -or $references.Count -gt 9)) { throw 'Sparse query reference count must be 1..9.' }
    if ($query.kind -eq 'negative' -and $references.Count -ne 0) { throw 'Negative queries cannot have relevant references.' }
    $hits = @($query.hits | Select-Object -First 10)
    $seenEvents = @()
    $useful = 0
    $duplicates = 0
    foreach ($hit in $hits) {
        if (-not $hit.eventId -or $null -eq $hit.grade -or ($hit.grade -isnot [int] -and $hit.grade -isnot [long]) -or $hit.grade -notin @(0,1,2,3)) { throw 'Every hit needs an eventId and a judged integer grade.' }
        if ($hit.grade -ge 2 -and $hit.eventId -notin $references) { throw 'Useful labels must match a reference event.' }
        if ($hit.eventId -in $seenEvents) { $duplicates++; continue }
        $seenEvents += $hit.eventId
        if ($hit.grade -ge 2) { $useful++ }
    }
    $u10 = $useful / 10.0
    $results += [pscustomobject]@{
        queryId = $query.id; kind = $query.kind; returnedTop10 = $hits.Count
        usefulIndependentEvents = $useful; duplicateSlots = $duplicates
        usefulRateAt10 = $u10
        mainMetricPassed = if ($query.kind -eq 'main') { $u10 -ge 0.7 } else { $null }
        recallAt10 = if ($references.Count -gt 0) { $useful / [double]$references.Count } else { $null }
        negativeReturnedAny = if ($query.kind -eq 'negative') { $hits.Count -gt 0 } else { $null }
    }
}
$mainQueries = @($results | Where-Object kind -eq 'main')
[pscustomobject]@{
    schemaVersion = 1; evidenceType = $benchmark.evidenceType; datasetId = $benchmark.datasetId
    queries = $results
    mainMetricPassed = if ($mainQueries.Count -gt 0) { @($mainQueries | Where-Object mainMetricPassed -eq $false).Count -eq 0 } else { $null }
    phase0QualityVerified = $false
    limitation = 'Metric calculation does not verify human labels, test independence, or model quality.'
} | ConvertTo-Json -Depth 8
