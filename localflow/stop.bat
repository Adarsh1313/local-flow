@echo off
rem Stops only Python processes running this checkout's localflow.py.
cd /d "%~dp0"
powershell -NoProfile -WindowStyle Hidden -Command "$script=(Resolve-Path 'localflow.py').Path; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like ('*' + $script + '*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Remove-Item -LiteralPath 'localflow.pid' -Force -ErrorAction SilentlyContinue"
