# PC-only · Supabase Storage (solo file)

Momentaneamente Eye/RandFatture resta sul **PC**. Supabase non è il database fatture: è solo lo **Storage** dei file caricati.

## Checklist go-live (PC hotel)

1. Copia `.env.example` → `.env` nella root del progetto, oppure in `%LOCALAPPDATA%\EyeSupremo\.env` se usi `EyeSupremo.exe`.
2. Su Supabase MultiHotel: esegui `.\applica-locazione-supabase.ps1` (oppure lo SQL in `supabase/migrations/20260922090000_eye_invoices_storage.sql`).
3. Incolla in `.env`:
   - `RANDFATTURE_SUPABASE_URL`
   - `RANDFATTURE_SUPABASE_SERVICE_KEY` (service role, **mai** nel browser)
   - `RANDFATTURE_SUPABASE_BUCKET=eye-invoices`
   - `RANDFATTURE_SUPABASE_CENTRAL_GATEWAY=https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway`
   - `RANDFATTURE_SUPABASE_CENTRAL_PIN` (+ opzionale `ANON_KEY`)
   - (opzionale PowerShell SQL) `RANDFATTURE_SUPABASE_DB_URL`
4. Avvia l’app: **`EyeSupremo.exe`** (finestra nativa consigliata) oppure `start.bat` in sviluppo.
5. Primo accesso: PIN **Sviluppatore**.
6. Impostazioni → PIN per **Caricatore** (e altri utenti).
7. Login Caricatore → carica un PDF/XML di prova.
8. Login operatore → **Coda Storage** → Anteprima → Conferma.
9. (Opzionale) `scarica-modelli-ia.bat` per `qwen3:4b` + `nomic-embed-text`.
Senza `.env` Supabase l’app resta operativa con mirror locale `data/supabase_mirror/` (o `%LOCALAPPDATA%\EyeSupremo\supabase_mirror` con l’exe).

## Flusso

1. **Sviluppatore** configura il PIN al primo avvio e assegna i PIN agli altri utenti (incluso `caricatore`).
2. **Caricatore** accede e vede solo *Carica fatture* → upload su Supabase Storage (o mirror locale).
3. All’upload viene calcolato lo **SHA-256**. Se esiste già in archivio → *Possibile duplicato*.
4. **Operatori** aprono *Coda Storage*, confrontano i doppioni, generano l’anteprima e confermano (o *Forza comunque*) l’import nel SQLite locale.

## Variabili `.env`

```env
RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co
RANDFATTURE_SUPABASE_SERVICE_KEY=eyJ...   # service role, solo sul PC
RANDFATTURE_SUPABASE_ANON_KEY=           # opzionale
RANDFATTURE_SUPABASE_BUCKET=eye-invoices
RANDFATTURE_SUPABASE_STORAGE_ROOT=invoices
RANDFATTURE_SUPABASE_CENTRAL_GATEWAY=https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway
RANDFATTURE_SUPABASE_CENTRAL_GATEWAY_ACTION=invoice_page
RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore
RANDFATTURE_SUPABASE_CENTRAL_PIN=        # PIN MultiHotel (non PIN locale Eye)
```

Senza queste variabili l’app usa `data/supabase_mirror/` (utile in sviluppo/test) con gli stessi path relativi.

## Bucket Supabase

Progetto MultiHotel (`ooqlfldcrnkudhgjnied`). Creare bucket + indice eseguendo
`supabase/migrations/20260922090000_eye_invoices_storage.sql` (vedi `docs/SUPABASE_INVOICES.md`).

Path content-addressable: `invoices/{xml|pdf|doc}/{hh}/{sha256}{ext}`.

La service key resta nel backend locale: non esporla nel frontend.

In app: la pagina **Fatture** elenca insieme archivio PC + metadati MultiHotel (quando `.env` è configurato). La **Coda Storage** resta per importare i file nel SQLite operativo.

## Ruoli

| Username     | Ruolo      | Capacità |
|--------------|------------|----------|
| sviluppatore | developer  | tutto + PIN utenti |
| supremo      | supremo    | operativo + coda |
| livello1–3   | level*     | operativo + coda |
| caricatore   | uploader   | solo upload file |

## Stati coda (UI)

| Codice | Etichetta IT |
|--------|----------------|
| `pending_review` | Da verificare |
| `possible_duplicate` | Possibile duplicato |
| `in_preview` | In anteprima |
| `imported` | Importata |
| `rejected` | Scartata |

## IA consigliata (16 GB RAM)

`qwen3:4b` + `nomic-embed-text` via Ollama. Non obbligatori per carico/coda.
