@echo off
rem Starts LocalFlow in the background (look for the mic icon in the tray).
cd /d "%~dp0"
rem Full paths, so stop.bat can find this instance.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0localflow.py"
