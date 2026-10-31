@echo off
rem Runs LocalFlow with a console window so you can see what's happening.
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0localflow.py"
pause
