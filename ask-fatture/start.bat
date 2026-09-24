@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Esegui prima setup.bat
  pause
  exit /b 1
)
start "Ask Fatture" /min cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe desktop.py"
endlocal
