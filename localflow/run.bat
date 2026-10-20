@echo off
rem Starts LocalFlow in the background (look for the mic icon in the tray).
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe localflow.py
