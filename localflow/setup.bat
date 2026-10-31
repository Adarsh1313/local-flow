@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path ([Environment]::GetFolderPath('Programs')) 'LocalFlow.lnk'; $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($p); $s.TargetPath=(Resolve-Path '.venv\Scripts\pythonw.exe').Path; $s.Arguments='"' + (Resolve-Path 'localflow.py').Path + '"'; $s.WorkingDirectory=(Resolve-Path '.').Path; $s.IconLocation=(Resolve-Path 'localflow.ico').Path; $s.Description='Private offline dictation and voice commands'; $s.Save()"
echo.
echo Setup done. Open LocalFlow from the Start menu or double-click run.bat.
pause
