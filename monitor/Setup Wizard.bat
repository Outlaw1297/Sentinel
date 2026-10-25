@echo off
setlocal
cd /d "%~dp0"

set "RELEASE=%~dp0dist\GnBotsMonitor-Release"
if exist "%RELEASE%\SentinelSetup.exe" (
    for /f "delims=" %%R in ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-release-runtime.ps1" -Quiet') do set "RELEASE=%%R"
    cd /d "%RELEASE%"
    "%RELEASE%\SentinelSetup.exe" %*
    exit /b %ERRORLEVEL%
)

if exist "%~dp0SentinelSetup.exe" (
    "%~dp0SentinelSetup.exe" %*
    exit /b %ERRORLEVEL%
)

powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\setup-wizard.ps1"
exit /b %ERRORLEVEL%
