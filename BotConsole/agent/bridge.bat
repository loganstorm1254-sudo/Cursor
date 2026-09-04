@echo off
title Beacon Console Bridge
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 bridge.py %*
  goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python bridge.py %*
  goto :eof
)

echo Python not found. Install Python and make sure "py" or "python" is on PATH.
pause
