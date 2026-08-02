@echo off
setlocal EnableExtensions
title Reel - Wi-Fi Movie Stream
cd /d "%~dp0"
set PORT=8080

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install from https://www.python.org/downloads/
  echo Check "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

if not exist "D:\Movies" (
  echo Creating D:\Movies ...
  mkdir "D:\Movies" 2>nul
)

echo.
echo  Opening Windows Firewall for port %PORT% so phones can connect...
netsh advfirewall firewall delete rule name="Reel Movie Stream" >nul 2>&1
netsh advfirewall firewall add rule name="Reel Movie Stream" dir=in action=allow protocol=TCP localport=%PORT% profile=any >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Firewall rule needs Administrator once.
  echo  Right-click Reel.bat -^> Run as administrator  ^(or click Yes on the UAC prompt^)
  echo.
  powershell -NoProfile -Command "Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=\"Reel Movie Stream\" dir=in action=allow protocol=TCP localport=%PORT% profile=any' -Verb RunAs -Wait" 2>nul
)

echo.
echo  Your phone Wi-Fi IPs on this PC:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do echo   %%a
echo.
echo  1^) Put movies in D:\Movies
echo  2^) On your PHONE install VLC
echo  3^) Open http://THIS-PC-IP:%PORT%/  ^(use an IP above, not 127.0.0.1^)
echo  4^) Tap a movie -^> Open in VLC  ^(that is how you get audio^)
echo.
echo  Leave this window open.
echo.

python "%~dp0stream.py" --movies "D:\Movies" --host 0.0.0.0 --port %PORT% --open
echo.
pause
