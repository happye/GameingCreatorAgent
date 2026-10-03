param(
    [string]$SourcePath,
    [switch]$Synthetic,
    [switch]$WithoutAudio,
    [ValidateRange(1, 30)][int]$DurationSeconds = 6
)

$ErrorActionPreference = 'Stop'
if (($Synthetic -and $SourcePath) -or (-not $Synthetic -and -not $SourcePath)) {
    throw 'Choose exactly one of -Synthetic or -SourcePath.'
}
if ($WithoutAudio -and -not $Synthetic) {
    throw '-WithoutAudio only applies to synthetic input.'
}
if ($SourcePath -and -not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw 'SourcePath must be a readable file.'
}
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$ffmpegPath = Join-Path $repositoryRoot '.tools/ffmpeg/bin/ffmpeg.exe'
$ffprobePath = Join-Path $repositoryRoot '.tools/ffmpeg/bin/ffprobe.exe'
if (-not (Test-Path -LiteralPath $ffmpegPath) -or -not (Test-Path -LiteralPath $ffprobePath)) {
    throw 'Prepare isolated FFmpeg tools in .tools/ffmpeg/bin first.'
}
$runDirectory = Join-Path $repositoryRoot ('artifacts/media-spike/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null

function Invoke-MediaTool {
    param([string]$Executable, [string[]]$ToolArguments, [string]$LogName)
    $toolOutput = & $Executable @ToolArguments 2> (Join-Path $runDirectory $LogName)
    if ($LASTEXITCODE -ne 0) {
        throw "Media command failed; inspect $LogName in $runDirectory"
    }
    return $toolOutput
}

$timer = [Diagnostics.Stopwatch]::StartNew()
if ($Synthetic) {
    $SourcePath = Join-Path $runDirectory '素材 测试.mp4'
    $generatorArguments = @('-hide_banner', '-nostdin', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30')
    if (-not $WithoutAudio) {
        $generatorArguments += @('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000')
    }
    $generatorArguments += @('-t', "$DurationSeconds", '-c:v', 'mpeg4')
    if (-not $WithoutAudio) { $generatorArguments += @('-c:a', 'aac') }
    $generatorArguments += $SourcePath
    Invoke-MediaTool $ffmpegPath $generatorArguments 'generate.log' | Out-Null
}
$SourcePath = (Resolve-Path -LiteralPath $SourcePath).Path
$probeOutput = Invoke-MediaTool $ffprobePath @('-v', 'error', '-show_format', '-show_streams', '-of', 'json', $SourcePath) 'probe.log'
$probeOutput | Set-Content -LiteralPath (Join-Path $runDirectory 'probe.json') -Encoding utf8
$probe = ($probeOutput -join "`n") | ConvertFrom-Json
if (@($probe.streams | Where-Object codec_type -eq 'video').Count -eq 0) {
    throw 'No video stream was found.'
}
$framePattern = Join-Path $runDirectory 'frame-%03d.jpg'
$filter = "trim=duration=$DurationSeconds,select=isnan(prev_selected_t)+gte(t-prev_selected_t\,1),scale=640:-2,showinfo"
Invoke-MediaTool $ffmpegPath @('-hide_banner', '-nostdin', '-n', '-i', $SourcePath, '-map', '0:v:0', '-vf', $filter, '-fps_mode', 'vfr', '-an', $framePattern) 'frames.log' | Out-Null
$frameTimes = @(Get-Content (Join-Path $runDirectory 'frames.log') | ForEach-Object {
    if ($_ -match 'pts_time:([0-9.eE+-]+)') {
        [double]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture)
    }
})
$frameCount = @(Get-ChildItem -LiteralPath $runDirectory -Filter 'frame-*.jpg').Count
if ($frameCount -eq 0 -or $frameCount -ne $frameTimes.Count) {
    throw 'Frame files and timestamp records do not match.'
}
for ($frameIndex = 1; $frameIndex -lt $frameTimes.Count; $frameIndex++) {
    if ($frameTimes[$frameIndex] -le $frameTimes[$frameIndex - 1]) { throw 'Non-increasing frame timestamps.' }
}
$audioStreams = @($probe.streams | Where-Object codec_type -eq 'audio')
$audioOutput = $null
if ($audioStreams.Count -gt 0) {
    $audioOutput = Join-Path $runDirectory 'audio.wav'
    Invoke-MediaTool $ffmpegPath @('-hide_banner', '-nostdin', '-n', '-i', $SourcePath, '-t', "$DurationSeconds", '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', $audioOutput) 'audio.log' | Out-Null
    $audioProbe = ((Invoke-MediaTool $ffprobePath @('-v', 'error', '-show_streams', '-of', 'json', $audioOutput) 'audio-probe.log') -join "`n") | ConvertFrom-Json
    if ($audioProbe.streams[0].sample_rate -ne '16000' -or $audioProbe.streams[0].channels -ne 1) {
        throw 'Unexpected audio format.'
    }
}
$timer.Stop()
$result = [ordered]@{
    schemaVersion = 1
    evidenceType = if ($Synthetic) { 'synthetic_media_smoke' } else { 'real_media_preprocessing_only' }
    sourceSha256 = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
    sourceDurationSeconds = $probe.format.duration
    sampleDurationLimitSeconds = $DurationSeconds
    frames = $frameCount
    decoderFrameTimesSeconds = $frameTimes
    hasAudio = $audioStreams.Count -gt 0
    audioExtracted = $null -ne $audioOutput
    elapsedSeconds = [math]::Round($timer.Elapsed.TotalSeconds, 3)
    apiCalls = 0
    semanticQualityVerified = $false
    limitations = @('No ASR or vision model called.', 'Decoder timestamps are not yet a persisted source-PTS mapping.', 'Short sample is not a source-hour throughput benchmark.')
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
Write-Host "Media preprocessing smoke passed: $runDirectory/result.json"
