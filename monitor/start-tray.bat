@echo off
setlocal
cd /d "%~dp0"

set "RELEASE=%~dp0dist\GnBotsMonitor-Release"
if exist "%RELEASE%\SentinelTray.exe" (
    for /f "delims=" %%R in ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-release-runtime.ps1" -Quiet') do set "RELEASE=%%R"
    start "" /B "%RELEASE%\SentinelTray.exe"
    exit /b %ERRORLEVEL%
)

if exist "%~dp0SentinelTray.exe" (
    start "" /B "%~dp0SentinelTray.exe"
    exit /b %ERRORLEVEL%
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-tray.ps1" -Force
exit /b %ERRORLEVEL%
