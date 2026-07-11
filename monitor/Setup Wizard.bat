@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0SentinelSetup.exe" (
    "%~dp0SentinelSetup.exe" %*
    exit /b %ERRORLEVEL%
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-wizard.ps1"
exit /b %ERRORLEVEL%
