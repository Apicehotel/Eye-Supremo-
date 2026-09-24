@echo off
setlocal
cd /d "%~dp0"
echo Scarico modello qwen3:8b (circa 5 GB)...
ollama pull qwen3:8b
if errorlevel 1 (
  echo Ollama non trovato o errore download. Installa da https://ollama.com
  pause
  exit /b 1
)
echo Modello pronto.
pause
endlocal
