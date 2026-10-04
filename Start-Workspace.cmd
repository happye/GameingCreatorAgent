@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-workspace.ps1" %*
if errorlevel 1 (
  echo.
  echo Workspace could not start. See the message and log paths above.
  pause
  exit /b 1
)
exit /b 0
