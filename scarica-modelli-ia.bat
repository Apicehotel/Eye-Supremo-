@echo off
setlocal
cd /d "%~dp0"
echo Installazione IA locale per Eye Supremo...
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama non trovato: installazione automatica in corso...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://ollama.com/install.ps1 | iex"
)
set "OLLAMA_EXE="
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE for /f "delims=" %%I in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%I"
if not defined OLLAMA_EXE (
  echo Impossibile trovare Ollama. Eye Supremo funzionera comunque in modalita locale deterministica.
  if /i not "%1"=="/silent" pause
  exit /b 1
)
echo Avvio del servizio Ollama locale...
start "" /b "%OLLAMA_EXE%" serve >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; 1..30 | %% { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if(-not $ok){ exit 1 }"
if errorlevel 1 goto :ollama_failed
echo.
echo Layer mirror IA: veloce su PC ufficio, qualita solo se serve.
echo.
echo [1/3] Llama 3.2 3B - layer veloce (mirror, default)...
"%OLLAMA_EXE%" pull llama3.2:3b || goto :failed
echo.
echo [2/3] Qwen 3 8B - layer qualita (escalation)...
"%OLLAMA_EXE%" pull qwen3:8b || goto :failed
echo.
echo [3/3] Qwen3 Embedding 0.6B - indice semantico leggero...
"%OLLAMA_EXE%" pull qwen3-embedding:0.6b || goto :failed
echo.
echo Modelli IA pronti (fast_first). Eye Supremo si aprira automaticamente.
if /i not "%1"=="/silent" pause
exit /b 0
:ollama_failed
echo Ollama non e disponibile o non ha avviato il servizio locale.
if /i not "%1"=="/silent" pause
exit /b 1
:failed
echo Download IA non completato. Rilanciare questo file per riprovare.
if /i not "%1"=="/silent" pause
exit /b 1
