@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not %errorlevel%==0 (
  echo Requesting Administrator approval to fully stop GnBots and emulators...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

echo Stopping GnBots API bot run...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-gnbots-now.ps1"

echo.
echo Force-killing GnBots and emulators...
taskkill /F /IM GnBots.exe /T >nul 2>&1
taskkill /F /IM dnplayer.exe /T >nul 2>&1
taskkill /F /IM Ld9BoxHeadless.exe /T >nul 2>&1
taskkill /F /IM adb.exe /T >nul 2>&1

timeout /t 2 /nobreak >nul
echo.
echo Remaining processes:
tasklist /FI "IMAGENAME eq GnBots.exe" 2>nul | find /I "GnBots.exe" && echo   GnBots still running || echo   GnBots: stopped
tasklist /FI "IMAGENAME eq dnplayer.exe" 2>nul | find /I "dnplayer.exe" && echo   dnplayer still running || echo   dnplayer: stopped
tasklist /FI "IMAGENAME eq Ld9BoxHeadless.exe" 2>nul | find /I "Ld9BoxHeadless.exe" && echo   Ld9BoxHeadless still running || echo   Ld9BoxHeadless: stopped
echo.
echo Done. Suppress flag set so the watcher will not auto-relaunch.
pause
