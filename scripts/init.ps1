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
    'docs/design-docs/adr-001-phase-0-language.md',
    'docs/design-docs/phase-0-engineering-spec.md',
    'docs/references/phase-0-benchmark.md',
    'docs/references/isolated-environment.md',
    'scripts/env.ps1',
    'scripts/toolchain.ps1',
    'scripts/setup-env.ps1',
    'scripts/verify.ps1',
    'toolchain.json',
    'pyproject.toml',
    'uv.lock',
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

. (Join-Path $PSScriptRoot 'env.ps1')
. (Join-Path $PSScriptRoot 'toolchain.ps1')
$missingTools = @()
try { Assert-ProjectToolchain -RepositoryRoot $repositoryRoot -RequireVenv }
catch { $missingTools += $_.Exception.Message }
foreach ($mediaTool in @('ffmpeg.exe', 'ffprobe.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".tools/ffmpeg/bin/$mediaTool"))) {
        $missingTools += "project-local $mediaTool"
    }
}

if ($missingTools.Count -gt 0) {
    Write-Host "Missing core Python/media prerequisites: $($missingTools -join ', ')."
    Write-Host 'Prepare isolated tools under .tools; do not install packages or modify system configuration.'
    exit 1
}

Write-Host 'Pinned project-local uv, CPython runtime/venv and media tools are available. Run scripts/verify.ps1 for F001 checks; ASR readiness requires F003.'
