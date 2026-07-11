# Starts the GnBots monitor tray icon (single instance).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-tray.ps1" -Force
exit /b %ERRORLEVEL%
