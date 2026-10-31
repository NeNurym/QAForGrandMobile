@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "quiet_run=0"
for %%A in (%*) do if /i "%%~A"=="--no-open" set "quiet_run=1"
echo.
echo INPUT:  %~dp0input
echo RESULT: %~dp0result
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -X utf8 workflow.py %*
) else (
  python -X utf8 workflow.py %*
)
if errorlevel 1 (
  echo.
  echo Processing failed. Read the message above.
  if "%quiet_run%"=="0" pause
  exit /b 1
)
if "%quiet_run%"=="1" exit /b 0
start "" "%~dp0result\index.html"
echo.
echo Done. Open result\index.html to view all rows and changes.
pause
