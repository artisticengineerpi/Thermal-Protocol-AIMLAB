@echo off
setlocal
cd /d "%~dp0"
"C:\Program Files\PsychoPy\python.exe" check_connection.py %*
pause
