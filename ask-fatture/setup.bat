@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PYRUN=py -3") else (set "PYRUN=python")
%PYRUN% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Setup Ask Fatture completato.
echo 1) Installa/avvia Ollama
echo 2) Esegui scarica-modello.bat
echo 3) Esegui start.bat
pause
endlocal
