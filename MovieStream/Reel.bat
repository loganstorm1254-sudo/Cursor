@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Reel - Wi-Fi Movie Stream
cd /d "%~dp0"
set PORT=8787
set MOVIES=D:\Movies

rem ---- always run elevated so firewall + bind work ----
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator so your phone can connect...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

rem ---- find Python ----
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py" && set "PYARGS=-3"
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python" && set "PYARGS="
)
if not defined PYEXE (
  echo.
  echo Python not found. Install from https://www.python.org/downloads/
  echo Check "Add python.exe to PATH", reboot, run this again.
  pause
  exit /b 1
)

if not exist "%MOVIES%" (
  echo Creating %MOVIES% ...
  mkdir "%MOVIES%" 2>nul
)

echo.
echo [1/4] Opening Windows Firewall for phones...
for /f "delims=" %%P in ('where python 2^>nul') do (
  netsh advfirewall firewall delete rule name="Reel Python" >nul 2>&1
  netsh advfirewall firewall add rule name="Reel Python" dir=in action=allow program="%%P" enable=yes profile=any >nul 2>&1
)
where py >nul 2>&1 && for /f "delims=" %%P in ('where py 2^>nul') do (
  netsh advfirewall firewall delete rule name="Reel Py Launcher" >nul 2>&1
  netsh advfirewall firewall add rule name="Reel Py Launcher" dir=in action=allow program="%%P" enable=yes profile=any >nul 2>&1
)
netsh advfirewall firewall delete rule name="Reel Movie Stream" >nul 2>&1
netsh advfirewall firewall add rule name="Reel Movie Stream" dir=in action=allow protocol=TCP localport=%PORT% enable=yes profile=any >nul 2>&1
echo      OK - port %PORT% allowed.

echo.
echo [2/4] Looking for movies in %MOVIES% ...
set COUNT=0
for /f "delims=" %%F in ('dir /s /b "%MOVIES%\*.mp4" "%MOVIES%\*.mkv" "%MOVIES%\*.m4v" "%MOVIES%\*.webm" "%MOVIES%\*.mov" "%MOVIES%\*.avi" 2^>nul') do (
  set /a COUNT+=1
  if !COUNT! LEQ 10 echo      - %%~nxF
)
if %COUNT% EQU 0 (
  echo.
  echo      *** NO movies found in %MOVIES% ***
  echo      Copy .mp4 / .mkv files into that folder, then press a key.
  explorer "%MOVIES%"
  pause
) else (
  echo      Found %COUNT% video file^(s^).
)

echo.
echo [3/4] Finding this PC's Wi-Fi address...
set PHONEIP=
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' }; $wifi = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' -and ($_.Name -match 'Wi-?Fi|Wireless') }; if ($wifi) { $w = $ips | Where-Object { $_.InterfaceIndex -eq $wifi[0].ifIndex -and $_.IPAddress -like '192.168.*' } | Select-Object -First 1; if ($w) { $w.IPAddress; exit } }; $pref = $ips | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -First 1; if (-not $pref) { $pref = $ips | Where-Object { $_.IPAddress -like '10.*' } | Select-Object -First 1 }; if (-not $pref) { $pref = $ips | Select-Object -First 1 }; if ($pref) { $pref.IPAddress }"`) do set PHONEIP=%%I
if not defined PHONEIP (
  for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set CAND=%%a
    set CAND=!CAND: =!
    echo !CAND! | findstr /r "^192\.168\." >nul && if not defined PHONEIP set PHONEIP=!CAND!
  )
)
if not defined PHONEIP set PHONEIP=REPLACE_WITH_IP_FROM_BELOW

echo.
echo ================================================================
echo   SCAN THE QR ON THE PC PAGE  - or open on your phone:
echo.
echo      http://%PHONEIP%:%PORT%/
echo.
echo   Same Wi-Fi. Do NOT use 127.0.0.1 on the phone.
echo   Tap a movie -^> Open in VLC for audio.
echo ================================================================
echo.

(
  echo Open this URL on your phone while Reel.bat is running:
  echo.
  echo http://%PHONEIP%:%PORT%/
  echo.
  echo Same Wi-Fi as the PC. Scan the QR on the PC browser page.
  echo Tap a movie -^> Open in VLC for audio.
) > "%~dp0PHONE-URL.txt"

echo [4/4] Starting Reel...
echo Leave this window OPEN while watching.
echo.
"%PYEXE%" %PYARGS% "%~dp0stream.py" --movies "%MOVIES%" --host 0.0.0.0 --port %PORT% --announce "%PHONEIP%" --open
echo.
echo Server stopped.
pause
