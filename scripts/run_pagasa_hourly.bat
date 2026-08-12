@echo off
setlocal
cd /d "%~dp0.."

if not exist logs mkdir logs

".venv\Scripts\python.exe" "scripts\update_geofences.py" >> "logs\pagasa_hourly.log" 2>&1

endlocal