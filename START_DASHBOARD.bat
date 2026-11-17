@echo off
setlocal
cd /d "%~dp0"
python dashboard\server.py
if errorlevel 1 (
  echo.
  echo Dashboard exited with an error. Check that Python 3.10 or later is installed.
  pause
)
