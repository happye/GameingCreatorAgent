# Dot-source only in the current process. No user/system environment changes.
$projectEnvironmentRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:UV_PYTHON, Env:UV_CONFIG_FILE, Env:VIRTUAL_ENV, Env:CONDA_PREFIX -ErrorAction SilentlyContinue
Remove-Item Env:UV_PYTHON_DOWNLOADS_JSON_URL, Env:UV_PYTHON_INSTALL_MIRROR, Env:UV_PYTHON_CPYTHON_BUILD, Env:PIP_TARGET, Env:PIP_PREFIX, Env:PIP_USER -ErrorAction SilentlyContinue
Remove-Item Env:UV_INDEX, Env:UV_EXTRA_INDEX_URL, Env:UV_DEFAULT_INDEX, Env:UV_INDEX_URL, Env:UV_FIND_LINKS, Env:UV_NO_INDEX -ErrorAction SilentlyContinue
Remove-Item Env:UV_PROJECT, Env:UV_WORKING_DIR -ErrorAction SilentlyContinue
$env:UV_PYTHON_DOWNLOADS = 'never'
$env:PIP_CONFIG_FILE = 'NUL'
$env:PIP_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/pip'
$env:PIP_REQUIRE_VIRTUALENV = '1'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONUTF8 = '1'
# The toolchain receipt hashes stdlib bytecode. Writing it back makes verify fail.
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $projectEnvironmentRoot '.cache/pycache'
$env:UV_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/uv'
$env:UV_PYTHON_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/python-downloads'
$env:UV_CREDENTIALS_DIR = Join-Path $projectEnvironmentRoot '.cache/uv-credentials'
$env:UV_NO_CONFIG = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectEnvironmentRoot '.tools/python'
$env:UV_PYTHON_BIN_DIR = Join-Path $projectEnvironmentRoot '.tools/python-bin'
$env:UV_PYTHON_INSTALL_BIN = '0'
$env:UV_PYTHON_INSTALL_REGISTRY = '0'
$env:UV_PYTHON_NO_REGISTRY = '1'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $projectEnvironmentRoot '.venv'
$env:UV_TOOL_DIR = Join-Path $projectEnvironmentRoot '.tools/uv-tools'
$env:UV_TOOL_BIN_DIR = Join-Path $projectEnvironmentRoot '.tools/uv-bin'
$env:RUFF_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/ruff'
$env:MYPY_CACHE_DIR = Join-Path $projectEnvironmentRoot '.cache/mypy'
$env:HF_HOME = Join-Path $projectEnvironmentRoot '.cache/huggingface'
$env:TORCH_HOME = Join-Path $projectEnvironmentRoot '.cache/torch'
$env:XDG_CACHE_HOME = Join-Path $projectEnvironmentRoot '.cache/xdg'
$env:TEMP = Join-Path $projectEnvironmentRoot '.cache/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$projectToolDirectories = @((Join-Path $projectEnvironmentRoot '.tools/uv'), (Join-Path $projectEnvironmentRoot '.venv/Scripts'), (Join-Path $projectEnvironmentRoot '.tools/ffmpeg/bin'))
$projectRemainingPath = @($env:PATH -split [IO.Path]::PathSeparator | Where-Object { $_ -notin $projectToolDirectories })
$env:PATH = ($projectToolDirectories + $projectRemainingPath) -join [IO.Path]::PathSeparator
