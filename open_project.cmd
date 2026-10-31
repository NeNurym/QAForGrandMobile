@echo off
setlocal
cd /d "%~dp0"
if not exist "presentation.html" (
  echo presentation.html was not found next to this launcher.
  pause
  exit /b 1
)
if /i "%~1"=="--check" exit /b 0
start "" "%~dp0presentation.html"
