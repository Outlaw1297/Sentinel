@echo off
setlocal
cd /d "%~dp0"
echo Installing UAC-free GnBots launch/close tasks...
echo A one-time Administrator prompt may appear.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure-elevated-tasks.ps1" -Force %*
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo Failed with exit code %ERR%.
) else (
  echo Done. Remote Launch/Close GnBots should work without UAC.
)
pause
exit /b %ERR%
