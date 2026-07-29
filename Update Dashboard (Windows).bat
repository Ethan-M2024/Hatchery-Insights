@echo off
REM Double-click this file to fetch the newest WDFW reports and rebuild the dashboard.
setlocal
cd /d "%~dp0"
cls
echo ===================================================================
echo   WDFW Hatchery Escapement Dashboard - update
echo ===================================================================
echo.

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (python --version >nul 2>&1 && set "PY=python")

if not defined PY (
  echo   Python 3.9 or newer is required and was not found.
  echo.
  echo   Install it from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add python.exe to PATH" on the first screen.
  echo   Then double-click this file again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo   First run: setting up a private Python environment ^(about a minute^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo   Could not create the .venv folder.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip >nul 2>&1
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo   Could not install the requirements.
  pause
  exit /b 1
)

python src\pipeline.py %*
set STATUS=%ERRORLEVEL%

echo.
if "%STATUS%"=="0" (
  echo   Done. The dashboard should have opened in your browser.
) else (
  echo   The update finished with problems - see the messages above.
)
echo.
pause
