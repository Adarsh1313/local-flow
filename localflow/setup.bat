@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Setup done. Double-click run.bat to start.
pause
