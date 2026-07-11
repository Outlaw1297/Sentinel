@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv venv
)

call venv\Scripts\activate.bat
python -m pip install -r requirements.txt -q

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-run-elevation.ps1" "%~dp0"
if %ERRORLEVEL% EQU 0 exit /b 0

echo.
echo Sentinel starting on http://localhost:8787
echo Press Ctrl+C to stop.
echo.

python app.py
