@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0Sentinel.exe" (
    "%~dp0Sentinel.exe" %*
    exit /b %ERRORLEVEL%
)

:: Self-elevate once so the whole headless stack runs as admin (GnBots requires it).
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -STA -File "%~dp0scripts\stack-splash.ps1" -Elevated
exit /b %ERRORLEVEL%
