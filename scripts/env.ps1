# Dot-source only in the current process. No user/system environment changes.
$projectEnvironmentRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:DOTNET_ROOT = Join-Path $projectEnvironmentRoot '.tools/dotnet'
$env:DOTNET_CLI_HOME = Join-Path $projectEnvironmentRoot '.cache/dotnet-home'
$env:DOTNET_MULTILEVEL_LOOKUP = '0'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:NUGET_PACKAGES = Join-Path $projectEnvironmentRoot '.cache/nuget'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $projectEnvironmentRoot '.cache/nuget-http'
$env:NUGET_PLUGINS_CACHE_PATH = Join-Path $projectEnvironmentRoot '.cache/nuget-plugins'
$env:NUGET_SCRATCH = Join-Path $projectEnvironmentRoot '.cache/nuget-scratch'
$env:PIP_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/pip'
$env:PIP_REQUIRE_VIRTUALENV = '1'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $projectEnvironmentRoot '.cache/pycache'
$env:UV_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectEnvironmentRoot '.tools/python'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $projectEnvironmentRoot '.venv'
$env:HF_HOME = Join-Path $projectEnvironmentRoot '.cache/huggingface'
$env:TORCH_HOME = Join-Path $projectEnvironmentRoot '.cache/torch'
$env:XDG_CACHE_HOME = Join-Path $projectEnvironmentRoot '.cache/xdg'
$env:TEMP = Join-Path $projectEnvironmentRoot '.cache/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$projectToolDirectories = @($env:DOTNET_ROOT, (Join-Path $projectEnvironmentRoot '.venv/Scripts'), (Join-Path $projectEnvironmentRoot '.tools/ffmpeg/bin'))
$projectRemainingPath = @($env:PATH -split [IO.Path]::PathSeparator | Where-Object { $_ -notin $projectToolDirectories })
$env:PATH = ($projectToolDirectories + $projectRemainingPath) -join [IO.Path]::PathSeparator
