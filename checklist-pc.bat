@echo off
setlocal
echo === Eye / RandFatture · checklist PC ===
echo.

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo [OK] Creato .env da .env.example — inserisci URL e service key Supabase.
  ) else (
    echo [!] .env.example mancante.
  )
) else (
  echo [OK] .env presente.
)

findstr /C:"RANDFATTURE_SUPABASE_URL=https" .env >nul 2>nul
if errorlevel 1 (
  echo [..] Supabase URL non configurato: userai mirror locale data\supabase_mirror
) else (
  echo [OK] Supabase URL impostato in .env
)

echo.
echo Avvio consigliato: setup.bat  (una volta) poi start.bat
echo Doc: docs\PC_STORAGE.md
echo.
echo Locazione Supabase (bucket + SQL):
echo   powershell -ExecutionPolicy Bypass -File .\applica-locazione-supabase.ps1
echo.
pause
endlocal
