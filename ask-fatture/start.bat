@echo off
setlocal
cd /d "%~dp0"

REM Preferisci l'exe installato / buildato se presente
if exist "%~dp0AskFatture.exe" (
  start "" "%~dp0AskFatture.exe"
  endlocal
  exit /b 0
)
if exist "%~dp0..\dist\AskFatture.exe" (
  start "" "%~dp0..\dist\AskFatture.exe"
  endlocal
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo Esegui prima setup.bat  ^(oppure installa EyeSupremo-Setup.exe^)
  pause
  exit /b 1
)
start "Ask Fatture" /min cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe desktop.py"
endlocal
