@echo off
title Reel - Wi-Fi Movie Stream
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked, then run this again.
  pause
  exit /b 1
)

if not exist "D:\Movies" (
  echo Creating D:\Movies ...
  mkdir "D:\Movies" 2>nul
)

echo.
echo  Reel — streaming D:\Movies over Wi-Fi
echo  Leave this window open. On your phone open the Phones/TV URL below.
echo.
python "%~dp0stream.py" --movies "D:\Movies" --port 8080 --open
echo.
pause
