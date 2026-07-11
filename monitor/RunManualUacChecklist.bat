@echo off
setlocal
cd /d "%~dp0"
echo Sentinel manual UAC checklist (hung monitor recovery + elevated tasks).
echo You will be prompted for Administrator approval once.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-manual-uac-checklist.ps1"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo UAC checklist failed. See logs\uac-checklist-results.json
  pause
  exit /b %ERR%
)
echo UAC checklist passed. See logs\uac-checklist-results.json
pause
