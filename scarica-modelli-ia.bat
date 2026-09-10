@echo off
echo Download Qwen 3 8B per RandFatture...
ollama pull qwen3:8b
echo.
echo Download Llama 3.2 3B come modello alternativo...
ollama pull llama3.2:3b
echo.
echo Download modello embedding locale...
ollama pull nomic-embed-text
echo.
echo Modelli installati. In RandFatture usa qwen3:8b come modello chat.
pause
