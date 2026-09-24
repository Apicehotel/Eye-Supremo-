# Ask Fatture

Programmino **separato** da Eye Supremo / RandAI.

Serve a:
1. Importare fatture (XML FatturaPA)
2. **Catalogare** per **fornitore** (ragione sociale, nome commerciale, P.IVA, CF, indirizzo, scontistiche) e per **prodotto**
   - Su ogni prodotto: numero + tendina **Chili / Litri / Pezzi** (es. 40 Chili, 12 Pezzi): vale per tutti e ricalcola i prezzi
3. **Scartare il rumore** (carburante, sconti a riga, bollo, CONAI, trasporto…)
4. Salvare **prezzo unitario** (come in fattura) e **prezzo normalizzato** confrontabile:
   - peso: conf 50g a 2€ → **40 €/kg**; bombolone 3kg a 30€ → **10 €/kg**
   - litri: bottiglia 1,5L a 1,50€ → **1 €/l**; 0,002 €/ml → **2 €/l**; UM `LT` resta **€/l**
   - solo pezzo (senza kg/l in descrizione): normalizzato = **prezzo unitario €/pz**
5. Chiedere in italiano cose tipo *«quanto pago il latte?»*, *«dove lo pago meno?»*
6. Rispondere **solo** con i dati utili, via **Ollama locale**

Niente cloud, niente RandAI, niente magazzino Eye.

Versione corrente: **0.3.0** (`app/version.py`).

## Modello locale (default)

| Modello | Peso circa | Perché |
|---------|------------|--------|
| **`qwen3:8b`** (default) | ~5 GB | Più preciso su italiano e confronti prezzo; ancora locale e veloce su PC moderni |
| `qwen3:4b` | ~2,5 GB | Compromesso se la RAM è ~8–12 GB |
| `qwen3:1.7b` | ~1,4 GB | Massimo snappy / PC più deboli |

Cambia modello con variabile `ASKFATTURE_MODEL`.

## Requisiti

- Windows 10/11 (WebView2)
- [Ollama](https://ollama.com) installato e avviato (per le domande)

## Installer Windows (`.exe`)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_ask_fatture.ps1
```

Produce `dist\AskFatture.exe`. Con Inno Setup 6:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\AskFatture.iss
```

→ `release\AskFatture-Setup.exe`

- Doppio clic → finestra nativa **Ask Fatture** (niente browser, niente console)
- Dati in `%LOCALAPPDATA%\AskFatture`
- Dopo l’install: esegui `scarica-modello.bat` (accanto all’exe) se Ollama non ha già `qwen3:8b`

CI: workflow `windows-installer.yml` costruisce e fa smoke test headless di entrambi gli exe (Eye Supremo + Ask Fatture).

Release: Actions → **Publish Eye Supremo Release** pubblica anche `AskFatture-Setup.exe`.

## Avvio sviluppo (senza installer)

```bat
setup.bat
scarica-modello.bat
start.bat
```

`start.bat` usa `AskFatture.exe` se lo trova, altrimenti `desktop.py` nel venv.

Sviluppo solo API:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8787
```

## Flusso

1. **Importa** un XML FatturaPA  
2. Apri **Prodotti** → imposta pack (**numero + Chili/Litri/Pezzi**) se manca in fattura  
3. **Chiedi** (“quanto costa il latte?”, “fornitore più economico per la pasta?”)  

I file restano in `%LOCALAPPDATA%\AskFatture` (Windows) o `./data`.
