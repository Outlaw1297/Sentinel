@echo off
setlocal
cd /d "%~dp0"

echo Sentinel installer
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-headless.ps1" -LaunchWizard
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  echo Install exited with code %ERR%.
) else (
  echo Install complete.
)
pause
exit /b %ERR%
