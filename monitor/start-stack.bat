@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-stack.ps1"
exit /b %ERRORLEVEL%
