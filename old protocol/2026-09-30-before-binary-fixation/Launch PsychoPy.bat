@echo off
setlocal
cd /d "%~dp0"
set "AIMLAB_PYTHON=C:\Program Files\PsychoPy\python.exe"
if not exist "%AIMLAB_PYTHON%" (
  echo PsychoPy Python was not found at %AIMLAB_PYTHON%
  pause
  exit /b 1
)
"%AIMLAB_PYTHON%" run_experiment.py %*
if errorlevel 1 pause
