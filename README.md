# RandFatture

RandFatture è un gestionale locale-first per archiviare fatture aziendali, normalizzare prodotti e unità, analizzare prezzi e interrogare lo storico con Ollama. Il gestionale continua a funzionare quando Ollama è spento: database, import, ricerca, filtri, calcoli, report, backup e log sono deterministici.

## Architettura

- React + TypeScript + Vite per l'interfaccia responsive.
- FastAPI + SQLAlchemy 2 per le API REST.
- SQLite in modalità WAL; schema predisposto alla migrazione PostgreSQL.
- File e backup nella cartella locale `data` (ignorata da Git).
- Login locale con PIN; ruolo **Caricatore** solo per upload file.
- Supabase opzionale **solo come Storage file** (non database fatture).
- Ollama opzionale (profilo light: `qwen3:4b` + `nomic-embed-text` per PC ~16 GB).

Le decisioni e i flussi sono descritti in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/PC_STORAGE.md](docs/PC_STORAGE.md) e [docs/SUPABASE_INVOICES.md](docs/SUPABASE_INVOICES.md) (bucket `eye-invoices` su MultiHotel). Copia `.env.example` in `.env` per configurare Storage. Su Windows puoi usare anche `checklist-pc.bat`.

## Requisiti e avvio

Servono Windows 10/11, Python 3.11+ e Node.js 20+. Ollama è facoltativo. Fare doppio clic su `setup.bat` una sola volta, quindi su `start.bat`. Il browser si apre su `http://127.0.0.1:5173`; le API sono documentate su `http://127.0.0.1:8000/api/docs`.

### Installer Windows (app nativa `.exe`)

Per un **programma vero** (finestra Eye Supremo, senza console nera e senza aprire il browser):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Produce `dist\EyeSupremo.exe`. Con Inno Setup 6, `installer\EyeSupremo.iss` crea `release\EyeSupremo-Setup.exe`.

- Doppio clic → si apre **solo la finestra dell’app** (WebView2 / Edge embedded).
- Nessun `cmd`, nessun Chrome/Edge con barra indirizzi.
- Fatture, import ed editor restano nel processo locale; dati in `%LOCALAPPDATA%\EyeSupremo`.
- Serve il runtime **Microsoft Edge WebView2** (già presente su Windows 10/11 aggiornati).
- In CI il workflow `windows-installer.yml` costruisce e fa smoke test headless dell’exe.

`start.bat` resta solo per sviluppo (Vite + browser).

### Aggiornamenti sui PC (senza girarli a mano)

1. Pubblica una **GitHub Release** con asset `EyeSupremo-Setup.exe`  
   (Actions → **Publish Eye Supremo Release**, oppure tag `v1.3.1`).
2. Su ogni PC, in **Impostazioni → Aggiornamenti**:
   - **Controlla ora** / **Scarica e installa**, oppure
   - attiva **Installa automaticamente** (all’avvio l’app scarica il Setup e lo lancia).
3. I dati restano in `%LOCALAPPDATA%\EyeSupremo`; l’installer aggiorna solo il programma.

Senza Release su GitHub i PC non vedono nulla di nuovo (il solo push su `main` non basta).

## Importazione

La pagina Importa accetta PDF, XML, DOCX, XLSX e PPTX. MarkItDown converte i documenti locali in Markdown per l'analisi; l'XML FatturaPA resta letto con il parser strutturato e il PDF mantiene il fallback pypdf. Ogni import crea un'anteprima con confidenza e avvisi prima della conferma. Hash SHA-256 e metadati contabili rilevano possibili duplicati. JPG/PNG/CSV sono validati in upload ma richiedono il parser OCR/tabellare della roadmap.

## Unità e prezzi

Le descrizioni originali restano immutate. La normalizzazione riconosce kg/g, L/ml, pezzi, rotoli, confezioni, scatole, metri, m²/m³ e paia. Prezzo dichiarato e normalizzato sono salvati separatamente.

## Ollama

Installare Ollama e avviare `scarica-modelli-ia.bat`. Lo script installa `qwen3:8b` come modello principale, `llama3.2:3b` come alternativa leggera e `nomic-embed-text` per gli embedding. URL e modello attivo si modificano in Impostazioni. RandAI recupera prima un insieme limitato di righe via SQL/fuzzy e passa soltanto quelle al modello, mostrando le fonti.

## Backup e test

Impostazioni → Backup crea uno ZIP locale con database, allegati e configurazione sotto `data/backups`.

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
cd ..\frontend
npm run build
```

I test coprono normalizzazione, prezzi, database, duplicati, API, ricerca, fallback Ollama e XML FatturaPA.

## Sicurezza

Nessuna telemetria o invio cloud. Upload limitati, estensioni consentite, nomi file generati, protezione path traversal nei download, hash e audit log. Per il futuro multiutente serviranno autenticazione, cifratura e ruoli.

## Troubleshooting

- **IA locale non disponibile**: avviare Ollama e verificare URL/modello; il resto funziona comunque.
- **Porta occupata**: liberare la porta 8000 o 5173.
- **PDF senza testo**: è una scansione; viene segnalata per revisione.
- **Browser non aperto**: visitare `http://127.0.0.1:5173`.

## Roadmap dichiarata

- OCR Tesseract per scansioni e immagini; import CSV/XLSX con mappatura.
- Conferma completa dell'anteprima UI e riconciliazione alias assistita.
- Embedding incrementali con indice vettoriale locale.
- Report PDF/XLSX e ripristino backup guidato.
- Multiutente con ruoli e cifratura; packaging Tauri come alternativa al PyInstaller attuale; PostgreSQL opzionale.
