@echo off
setlocal
cd /d "%~dp0"
echo Scarico modello veloce qwen3:1.7b (circa 1.4 GB)...
ollama pull qwen3:1.7b
if errorlevel 1 (
  echo Ollama non trovato o errore download. Installa da https://ollama.com
  pause
  exit /b 1
)
echo Modello pronto.
pause
endlocal
