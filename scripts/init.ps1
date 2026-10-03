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
$missingTools = @()
$localUv = Join-Path $repositoryRoot '.tools/uv/uv.exe'
if (Test-Path -LiteralPath $localUv) {
    $uvVersionText = (& $localUv --version) -join "`n"
    $uvCheckExit = $LASTEXITCODE
    if ($uvCheckExit -ne 0 -or $uvVersionText -notmatch '^uv (\d+\.\d+\.\d+)\b') {
        $missingTools += 'working project-local uv >=0.11.8 (.tools/uv)'
    } elseif ([version]$Matches[1] -lt [version]'0.11.8') {
        $missingTools += 'uv >=0.11.8 supporting Python registry isolation'
    }
} else {
    $missingTools += 'project-local uv (.tools/uv)'
}
$localPython = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython) {
    $pythonCheckCode = 'import pathlib, sys, sysconfig; root = pathlib.Path(sys.argv[1]).resolve(); base = pathlib.Path(sys.base_prefix).resolve(); runtime = root / ".tools" / "python"; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 13); assert not sysconfig.get_config_var("Py_GIL_DISABLED"); assert pathlib.Path(sys.prefix).resolve() == root / ".venv"; assert base == runtime or runtime in base.parents; print(sys.version.split()[0])'
    & $localPython -I -c $pythonCheckCode $repositoryRoot | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $missingTools += 'CPython 3.13 venv backed by project-local runtime'
    }
} else {
    $missingTools += 'project-local CPython 3.13 venv (.venv)'
}
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

Write-Host 'Project-local uv, CPython 3.13 venv and media tools are available. Locked package versions and ASR readiness require F001/F003 checks.'
