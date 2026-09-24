# Ask Fatture

Programmino **separato** da Eye Supremo / RandAI.

Serve a:
1. Importare fatture (XML FatturaPA)
2. **Scartare il rumore** (carburante, sconti, bollo, CONAI, trasporto…)
3. Salvare **prezzo dichiarato** e **prezzo normalizzato** (€/kg, €/l… es. conf 50g a 2€ → 40 €/kg; bombolone 3kg a 30€ → 10 €/kg)
4. Chiedere in italiano cose tipo *«quanto pago il latte?»*, *«dove lo pago meno?»*
5. Rispondere **solo** con i dati utili, via **Ollama locale**

Niente cloud, niente RandAI, niente magazzino Eye.

## Modello locale (default)

| Modello | Peso circa | Perché |
|---------|------------|--------|
| **`qwen3:8b`** (default) | ~5 GB | Più preciso su italiano e confronti prezzo; ancora locale e veloce su PC moderni |
| `qwen3:4b` | ~2,5 GB | Compromesso se la RAM è ~8–12 GB |
| `qwen3:1.7b` | ~1,4 GB | Massimo snappy / PC più deboli |

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
