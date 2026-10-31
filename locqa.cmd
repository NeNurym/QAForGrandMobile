@echo off
if "%~1"=="" (
  call "%~dp0start_project.cmd"
  exit /b
)
python "%~dp0locqa.py" %*
