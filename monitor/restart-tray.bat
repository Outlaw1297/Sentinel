@echo off
setlocal
cd /d "%~dp0"

:: Tray runs elevated with the stack — restart it from an elevated prompt too.
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Approve UAC to restart the tray icon...
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b 0
)

set "RELEASE=%~dp0dist\GnBotsMonitor-Release"
if exist "%RELEASE%\SentinelTray.exe" (
    for /f "delims=" %%R in ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-release-runtime.ps1" -Quiet') do set "RELEASE=%%R"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-tray.ps1" -Quiet
    timeout /t 1 /nobreak >nul
    start "" /B "%RELEASE%\SentinelTray.exe"
    echo.
    echo Tray restarted. Right-click for menu, double-click to open dashboard.
    timeout /t 4 /nobreak >nul
    exit /b 0
)

echo Stopping tray icon...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-tray.ps1" -Quiet
timeout /t 1 /nobreak >nul

echo Starting tray icon...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-tray.ps1" -Force -Quiet

echo.
echo Tray restarted. Right-click for menu, double-click to open dashboard.
timeout /t 4 /nobreak >nul
exit /b 0
