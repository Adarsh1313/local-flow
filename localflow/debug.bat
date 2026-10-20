@echo off
rem Runs LocalFlow with a console window so you can see what's happening.
cd /d "%~dp0"
.venv\Scripts\python.exe localflow.py
pause
