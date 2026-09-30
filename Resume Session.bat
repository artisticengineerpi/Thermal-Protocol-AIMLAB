@echo off
setlocal
cd /d "%~dp0"
"C:\Program Files\PsychoPy\python.exe" resume_session.py
if errorlevel 1 pause
