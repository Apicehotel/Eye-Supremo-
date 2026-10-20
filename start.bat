@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
  call .venv\Scripts\activate.bat
  python -m pip install -r backend\requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
if exist "dist\EyeSupremo\EyeSupremo.exe" (
  start "Eye Supremo" /min cmd /c "dist\EyeSupremo\EyeSupremo.exe"
) else (
  call start-dev.bat
)
endlocal
