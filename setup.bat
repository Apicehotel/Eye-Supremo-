@echo off
setlocal
cd /d "%~dp0"
echo Eye Supremo - ambiente di sviluppo
where py >nul 2>nul
if %errorlevel%==0 (set "PYRUN=py -3") else (set "PYRUN=python")
%PYRUN% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
call npm --prefix frontend install
echo.
echo Ambiente sviluppo pronto. Avvia con start.bat
echo Per il PC finale usa EyeSupremo-Setup.exe, che non richiede Python o Node.
pause
endlocal
