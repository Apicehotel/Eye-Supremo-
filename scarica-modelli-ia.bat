@echo off
setlocal
echo Installazione modelli IA light (PC ~16 GB RAM)...
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama non trovato. Installalo da https://ollama.com e rilancia questo file.
  pause
  exit /b 1
)
echo.
echo [1/2] Qwen3 4B - modello chat principale...
ollama pull qwen3:4b
echo.
echo [2/2] nomic-embed-text - embedding leggero...
ollama pull nomic-embed-text
echo.
echo Opzionale (solo se hai margine di RAM): ollama pull qwen3:8b
echo.
echo Modelli pronti. In Impostazioni usa qwen3:4b e nomic-embed-text.
pause
endlocal
