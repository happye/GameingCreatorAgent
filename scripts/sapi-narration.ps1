param(
    [Parameter(Mandatory=$true)][ValidateSet('list','synthesize')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$RequestPath
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$request = [IO.File]::ReadAllText($RequestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
$speaker = New-Object -ComObject SAPI.SpVoice
$tokens = $speaker.GetVoices()
$voices = @()
for ($i = 0; $i -lt $tokens.Count; $i++) {
    $token = $tokens.Item($i)
    $voices += @{voiceId=$token.Id; description=$token.GetDescription(); language=$token.GetAttribute('Language'); engine='windows-sapi'}
}
if ($Mode -eq 'list') {
    ConvertTo-Json -InputObject @($voices) -Compress
    exit 0
}
$selected = $null
for ($i = 0; $i -lt $tokens.Count; $i++) {
    if ($tokens.Item($i).Id -ceq $request.voiceId) { $selected = $tokens.Item($i); break }
}
if ($null -eq $selected) { throw 'Requested voice is no longer installed.' }
$speaker.Voice = $selected
$stream = New-Object -ComObject SAPI.SpFileStream
try {
    # SAFT22kHz16BitMono. Read the actual resulting PCM format in Python.
    $stream.Format.Type = 22
    $stream.Open([string]$request.wavPath, 3, $false)
    $speaker.AudioOutputStream = $stream
    # SVSFIsNotXML explicitly treats XML-looking user input as plain text.
    [void]$speaker.Speak([string]$request.text, 16)
} finally {
    $stream.Close()
}
ConvertTo-Json -InputObject @{voiceId=$selected.Id} -Compress
