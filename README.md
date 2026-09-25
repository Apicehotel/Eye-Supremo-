# Eye Supremo

Eye Supremo è un gestionale locale-first per archiviare fatture aziendali, normalizzare prodotti e unità, analizzare prezzi, gestire recensioni multi-hotel e interrogare lo storico con Ollama. Continua a funzionare quando Ollama è spento: database, import, ricerca, filtri, calcoli, report, backup e log sono deterministici.

> **Ask Fatture** (cartella `ask-fatture/`, v0.3.0) è incluso nell’**installer unico** `EyeSupremo-Setup.exe` insieme a Eye Supremo: import XML, catalogo fornitori/prodotti, pack **Chili / Litri / Pezzi**, domande con `qwen3:8b` locale. Non usa RandAI.

## Architettura

- React + TypeScript + Vite per l'interfaccia responsive.
- FastAPI + SQLAlchemy 2 per le API REST.
- SQLite in modalità WAL; schema predisposto alla migrazione PostgreSQL.
- File e backup nella cartella locale `data` (ignorata da Git) o `%LOCALAPPDATA%\EyeSupremo` con l’exe.
- Login locale con PIN; ruolo **Caricatore** solo per upload file.
- Supabase opzionale **solo come Storage file** + catalogo centrale MultiHotel (non database fatture PC).
- Ollama opzionale (profilo light: `qwen3:4b` + `nomic-embed-text` per PC ~16 GB).

Le decisioni e i flussi sono descritti in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/PC_STORAGE.md](docs/PC_STORAGE.md), [docs/SUPABASE_INVOICES.md](docs/SUPABASE_INVOICES.md) (bucket `eye-invoices` su MultiHotel) e [docs/SUPABASE_REVIEWS.md](docs/SUPABASE_REVIEWS.md) (`eye_central_reviews`). Copia `.env.example` in `.env` per configurare Storage. Su Windows puoi usare anche `checklist-pc.bat`.

## Requisiti e avvio

Servono Windows 10/11, Python 3.11+ e Node.js 20+. Ollama è facoltativo. Fare doppio clic su `setup.bat` una sola volta, quindi su `start.bat`. Il browser si apre su `http://127.0.0.1:5173`; le API sono documentate su `http://127.0.0.1:8000/api/docs`.

### Installer Windows (unico Setup)

Un solo installer per **Eye Supremo + Ask Fatture**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_suite.ps1
```

Oppure i passi singoli:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_ask_fatture.ps1
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\EyeSupremo.iss
```

Produce `release\EyeSupremo-Setup.exe` (v1.4.2) con:

- `EyeSupremo.exe` — gestionale (dati in `%LOCALAPPDATA%\EyeSupremo`)
- `AskFatture.exe` — domande/catalogo/pack Chili·Litri·Pezzi (dati in `%LOCALAPPDATA%\AskFatture`)
- collegamenti Start Menu / desktop per entrambi
- script per scaricare i modelli Ollama

Serve **Microsoft Edge WebView2**. CI: `windows-installer.yml` (smoke headless di entrambi gli exe + Setup unico).

`start.bat` resta solo per sviluppo (Vite + browser). Dettagli Ask Fatture in [ask-fatture/README.md](ask-fatture/README.md).

### Aggiornamenti sui PC (senza girarli a mano)

1. Pubblica una **GitHub Release** con asset `EyeSupremo-Setup.exe`  
   (Actions → **Publish Eye Supremo Release**, oppure tag `v1.4.2`).
   Download: https://github.com/Apicehotel/Eye-Supremo-/releases/latest
2. Su ogni PC, in **Impostazioni → Aggiornamenti**:
   - **Controlla ora** / **Scarica e installa**, oppure
   - attiva **Installa automaticamente**.
3. L’installer aggiorna entrambi i programmi; i dati restano nelle cartelle LocalAppData.

Senza Release su GitHub i PC non vedono nulla di nuovo (il solo push su `main` non basta).

## Variabili ambiente

Le variabili restano con prefisso `RANDFATTURE_` per compatibilità con i `.env` già in produzione (es. `RANDFATTURE_SUPABASE_URL`). Il nome prodotto mostrato in UI è **Eye Supremo**.

## Importazione

La pagina Importa accetta PDF, XML, DOCX, XLSX e PPTX. MarkItDown converte i documenti locali in Markdown per l'analisi; l'XML FatturaPA resta letto con il parser strutturato e il PDF mantiene il fallback pypdf. Ogni import crea un'anteprima con confidenza e avvisi prima della conferma. Hash SHA-256 e metadati contabili rilevano possibili duplicati. JPG/PNG/CSV sono validati in upload ma richiedono il parser OCR/tabellare della roadmap.

## Unità e prezzi

Le descrizioni originali restano immutate. La normalizzazione riconosce kg/g, L/ml, pezzi, rotoli, confezioni, scatole, metri, m²/m³ e paia. Prezzo dichiarato e normalizzato sono salvati separatamente.

## Ollama

Installare Ollama e avviare `scarica-modelli-ia.bat`. Lo script installa `qwen3:8b` come modello principale, `llama3.2:3b` come alternativa leggera e `nomic-embed-text` per gli embedding. URL e modello attivo si modificano in Impostazioni. Eye AI recupera prima un insieme limitato di righe via SQL/fuzzy e passa soltanto quelle al modello, mostrando le fonti.


## Modalità offline-first fatture

Eye Supremo usa il PC come fonte operativa primaria. In **Impostazioni → Modalità offline**:

- **Sincronizza catalogo** scarica tutte le pagine di `eye_central_invoices` e salva una copia locale in `%LOCALAPPDATA%\\EyeSupremo\\offline\\central_invoices.json`.
- **Prepara offline completo** salva anche i PDF/XML disponibili in Supabase Storage sotto `%LOCALAPPDATA%\\EyeSupremo\\offline\\documents`.
- La pagina **Fatture** legge prima la cache locale; se Internet cade continua a cercare e filtrare l'intero catalogo già sincronizzato.
- La cache viene sostituita solo a sincronizzazione completata: una caduta di rete non cancella mai l'ultima copia valida.
- Senza una cache iniziale, Eye Supremo mantiene il fallback live limitato finché non viene eseguita la prima sincronizzazione completa.

Supabase resta il punto di sincronizzazione/condivisione, non un requisito per usare l'archivio quotidiano.
\n## Backup e test

Impostazioni → Backup crea uno ZIP locale con database, allegati e configurazione sotto `data/backups` (o `%LOCALAPPDATA%\EyeSupremo\backups`).

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
