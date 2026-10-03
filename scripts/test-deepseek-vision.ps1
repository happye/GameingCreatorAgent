param([Parameter(Mandatory)][string]$SourcePath)

$ErrorActionPreference = 'Stop'
if (-not $env:DEEPSEEK_API_KEY) { throw 'Set DEEPSEEK_API_KEY in the current process before running this experiment.' }
$SourcePath = (Resolve-Path -LiteralPath $SourcePath).Path
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$ffmpegPath = Join-Path $repositoryRoot '.tools/ffmpeg/bin/ffmpeg.exe'
$ffprobePath = Join-Path $repositoryRoot '.tools/ffmpeg/bin/ffprobe.exe'
if (-not (Test-Path -LiteralPath $ffmpegPath) -or -not (Test-Path -LiteralPath $ffprobePath)) { throw 'Prepare project-local FFmpeg tools first.' }
$runDirectory = Join-Path $repositoryRoot ('artifacts/deepseek-spike/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$probeText = & $ffprobePath -v error -show_entries format=duration -of json $SourcePath
if ($LASTEXITCODE -ne 0) { throw 'Cannot probe input media.' }
$probe = ($probeText -join "`n") | ConvertFrom-Json
$duration = [double]::Parse($probe.format.duration, [Globalization.CultureInfo]::InvariantCulture)
$contentBlocks = @(@{ type = 'text'; text = 'Return a JSON object with observations: [{frameId,timeSeconds,visibleFacts,possibleMechanics,uncertainty}]. Describe only visible game content. Avoid guessing game names or causality. Static images cannot prove events between frames. Return one observation per supplied frame. Use Chinese for descriptions.' })
$sampleTimes = @()
for ($sampleIndex = 1; $sampleIndex -le 5; $sampleIndex++) {
    $sampleTime = [math]::Round($duration * $sampleIndex / 6, 3)
    $sampleTimes += $sampleTime
    $frameId = 'f{0:D3}' -f $sampleIndex
    $framePath = Join-Path $runDirectory "$frameId.jpg"
    $timeArgument = $sampleTime.ToString([Globalization.CultureInfo]::InvariantCulture)
    & $ffmpegPath -hide_banner -loglevel error -nostdin -n -ss $timeArgument -i $SourcePath -frames:v 1 -vf 'scale=768:-2' $framePath 2> (Join-Path $runDirectory "$frameId.log")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $framePath)) { throw 'Frame extraction failed.' }
    $contentBlocks += @{ type = 'text'; text = "frameId=$frameId sourceTimeSeconds=$timeArgument" }
    $contentBlocks += @{ type = 'image_url'; image_url = @{ url = 'data:image/jpeg;base64,' + [Convert]::ToBase64String([IO.File]::ReadAllBytes($framePath)); detail = 'original' } }
}
$metadata = [ordered]@{
    schemaVersion = 1
    modelRequested = 'deepseek-flash'
    sourceSha256 = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
    sourceDurationSeconds = $duration
    sampleTimesSeconds = $sampleTimes
    attempt = 1
    status = 'request_prepared'
    pricingSource = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
    pricingCheckedDate = '2026-10-03'
    apiCostStatus = 'unverified'
    semanticQualityVerified = $false
}
$metadataPath = Join-Path $runDirectory 'result.json'
$metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metadataPath -Encoding utf8
$body = @{ model = 'deepseek-flash'; thinking = @{type = 'disabled'}; max_tokens = 1600; response_format = @{type = 'json_object'}; messages = @(@{role = 'user'; content = $contentBlocks}) } | ConvertTo-Json -Depth 12 -Compress
$requestTimer = [Diagnostics.Stopwatch]::StartNew()
try {
    $webResponse = Invoke-WebRequest -Uri 'https://api.deepseek.com/chat/completions' -Method Post -Headers @{ Authorization = 'Bearer ' + $env:DEEPSEEK_API_KEY } -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 120
} catch {
    $metadata.status = 'request_failed'
    $metadata['httpStatus'] = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
    $metadata['elapsedSeconds'] = [math]::Round($requestTimer.Elapsed.TotalSeconds, 3)
    $metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metadataPath -Encoding utf8
    throw "DeepSeek request failed; sanitized metadata: $metadataPath"
}
$requestTimer.Stop()
$response = $webResponse.Content | ConvertFrom-Json
$webResponse.Content | Set-Content -LiteralPath (Join-Path $runDirectory 'response.json') -Encoding utf8
$metadata.status = 'response_received'
$metadata['responseId'] = $response.id
$metadata['modelReported'] = $response.model
$metadata['usage'] = $response.usage
$metadata['elapsedSeconds'] = [math]::Round($requestTimer.Elapsed.TotalSeconds, 3)
$metadata['finishReason'] = $response.choices[0].finish_reason
$observations = $null
try { $observations = $response.choices[0].message.content | ConvertFrom-Json } catch { $metadata.status = 'invalid_json_output' }
if ($observations) {
    $valid = @($observations.observations).Count -eq 5
    $seenFrameIds = @()
    foreach ($observation in $observations.observations) {
        $valid = $valid -and $observation.frameId -match '^f00[1-5]$'
        if ($observation.frameId -match '^f00([1-5])$') {
            $expectedTime = $sampleTimes[[int]$Matches[1] - 1]
            $valid = $valid -and [math]::Abs([double]$observation.timeSeconds - $expectedTime) -lt 0.01
        }
        $seenFrameIds += $observation.frameId
    }
    $valid = $valid -and @($seenFrameIds | Select-Object -Unique).Count -eq 5
    $metadata['structuredOutputValid'] = $valid -and $metadata.finishReason -ne 'length'
    $observations | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $runDirectory 'observations.json') -Encoding utf8
}
# Conservative high-period estimate avoids silently assuming the price period.
if ($response.usage -and $null -ne $response.usage.prompt_tokens -and $null -ne $response.usage.completion_tokens) {
    $metadata['apiCostUpperEstimateCny'] = ([double]$response.usage.prompt_tokens * 2 + [double]$response.usage.completion_tokens * 8) / 1000000
    $metadata.apiCostStatus = 'estimated_upper_bound_not_billing_confirmed'
}
$metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $metadataPath -Encoding utf8
Write-Host "DeepSeek vision experiment recorded: $metadataPath"
