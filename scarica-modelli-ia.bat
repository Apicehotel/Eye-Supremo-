@echo off
setlocal
echo Installazione modelli IA per Eye Supremo...
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama non trovato. Installalo da https://ollama.com e rilancia questo file.
  pause
  exit /b 1
)
echo.
echo [1/3] Qwen 3 8B - modello principale...
ollama pull qwen3:8b
echo.
echo [2/3] Llama 3.2 3B - fallback veloce...
ollama pull llama3.2:3b
echo.
echo [3/3] Qwen3 Embedding 0.6B - indice semantico leggero...
ollama pull qwen3-embedding:0.6b
echo.
echo Modelli pronti. Eye Supremo usa Qwen 3 8B per analisi e Qwen3 Embedding 0.6B per indicizzazione.
pause
endlocal
