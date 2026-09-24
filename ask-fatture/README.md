# Ask Fatture

Programmino **separato** da Eye Supremo / RandAI.

Serve a:
1. Importare fatture (XML FatturaPA)
2. Chiedere in italiano cose tipo *«quanto pago il latte?»*, *«dove lo pago meno?»*
3. Rispondere **solo** con i dati delle tue fatture, via **Ollama locale**

Niente cloud, niente RandAI, niente magazzino Eye.

## Modello locale (default)

| Modello | Peso circa | Perché |
|---------|------------|--------|
| **`qwen3:1.7b`** (default) | ~1,4 GB | Veloce, multilingua (italiano ok), buon compromesso 2025–26 |
| `qwen3:0.6b` | ~0,5 GB | Ancora più veloce, risposte più grezze |
| `qwen3:4b` | ~2,5 GB | Più preciso se il PC ha ~16 GB RAM |

Cambia modello in Impostazioni nell’app o con variabile `ASKFATTURE_MODEL`.

## Requisiti

- Windows 10/11 (o Linux/macOS)
- Python 3.11+
- [Ollama](https://ollama.com) installato e avviato

## Avvio

```bat
setup.bat
scarica-modello.bat
start.bat
```

Si apre la finestra **Ask Fatture** (WebView2) su `http://127.0.0.1:8787`.

Sviluppo senza finestra nativa:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8787
```

## Flusso

1. **Importa** un XML FatturaPA  
2. **Chiedi** (“quanto costa il latte?”, “fornitore più economico per la pasta?”)  
3. Il motore cerca le righe nell’archivio locale e chiede a Qwen3 di rispondere **solo** su quei dati  

I file restano in `%LOCALAPPDATA%\AskFatture` (Windows) o `./data`.
