@echo off

setlocal

cd /d "%~dp0"

echo Sentinel setup
echo Prepares the monitor environment and runs the desktop Setup Wizard when needed.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-headless.ps1" -LaunchWizard
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo Setup exited with code %ERR%.
) else (
  echo Setup complete.
)
pause
exit /b %ERR%
