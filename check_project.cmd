@echo off
setlocal
cd /d "%~dp0"

echo Running tests...
python -m unittest discover -s tests
if errorlevel 1 goto failed

echo Building the demo report...
python locqa.py check --source examples/demo/intl_ru.arb --target examples/demo/intl_kk.arb --glossary examples/demo/glossary.csv --suspect-phrases examples/demo/suspect_kk.txt --out reports/demo.json
if errorlevel 1 goto failed

python examples/demo/verify.py
if errorlevel 1 goto failed

echo Checks passed. Report: reports\demo.html
if /i "%~1"=="--no-open" exit /b 0
start "" "%~dp0reports\demo.html"
pause
exit /b 0

:failed
echo A check failed. Read the message above.
if /i "%~1"=="--no-open" exit /b 1
pause
exit /b 1
