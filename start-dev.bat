@echo off
setlocal
cd /d "%~dp0"
if not exist "frontend\node_modules" call npm --prefix frontend install
start "Eye Supremo API (sviluppo)" /min cmd /c "cd /d %~dp0backend && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Eye Supremo UI (sviluppo)" /min cmd /c "cd /d %~dp0frontend && npm run dev -- --host 127.0.0.1"
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5173
endlocal
