param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$requiredPaths = @(
    'AGENTS.md',
    'CODEX.md',
    'CLAUDE.md',
    '.grok/rules/project.md',
    'HANDOFF.md',
    'feature_list.json',
    'progress.md',
    'docs/product-specs/phase-0.md',
    'docs/design-docs/architecture.md',
    'docs/exec-plans/phase-0-plan.md',
    'docs/references/testing-guide.md',
    'docs/references/agent-workflow.md',
    'docs/exec-plans/assignments.md',
    'src',
    'tests'
)

foreach ($relativePath in $requiredPaths) {
    $absolutePath = Join-Path $repositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
        throw "Required scaffold path is missing: $relativePath"
    }
}

$featuresPath = Join-Path $repositoryRoot 'feature_list.json'
$featureData = Get-Content -LiteralPath $featuresPath -Raw -Encoding UTF8 | ConvertFrom-Json
$features = @($featureData.features)
if ($features.Count -eq 0) {
    throw 'feature_list.json has no features.'
}

$ids = @($features | ForEach-Object { $_.id })
if (@($ids | Select-Object -Unique).Count -ne $ids.Count) {
    throw 'feature_list.json has duplicate feature IDs.'
}

foreach ($feature in $features) {
    if ([string]::IsNullOrWhiteSpace($feature.id) -or
        [string]::IsNullOrWhiteSpace($feature.name) -or
        [string]::IsNullOrWhiteSpace($feature.test_criteria) -or
        $null -eq $feature.passes) {
        throw "Feature entry is incomplete: $($feature.id)"
    }
}

Write-Host "Scaffold valid: $($features.Count) Phase 0 features."
if ($CheckOnly) {
    return
}

$missingTools = @()
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
if ($null -eq $dotnetCommand -or @(& dotnet --list-sdks).Count -eq 0) {
    $missingTools += '.NET SDK'
}
if ($null -eq (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $missingTools += 'FFmpeg'
}

if ($missingTools.Count -gt 0) {
    Write-Host "Missing Phase 0 prerequisites: $($missingTools -join ', ')."
    Write-Host 'Install them and rerun this script before building the CLI.'
    exit 1
}

Write-Host 'Phase 0 prerequisites are available. No application project has been created yet.'
