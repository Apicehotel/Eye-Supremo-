@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PYRUN=py -3") else (set "PYRUN=python")
%PYRUN% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
call npm --prefix frontend install
echo Installazione completata. Avvia con start.bat
pause
endlocal
