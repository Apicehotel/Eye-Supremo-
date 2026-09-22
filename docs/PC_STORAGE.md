# PC-only · Supabase Storage (solo file)

Momentaneamente Eye/RandFatture resta sul **PC**. Supabase non è il database fatture: è solo lo **Storage** dei file caricati.

## Checklist go-live (PC hotel)

1. Copia `.env.example` → `.env` nella root del progetto (o accanto all’eseguibile).
2. Su Supabase: crea bucket privato `invoices` (Storage → New bucket → Private).
3. Incolla in `.env`:
   - `RANDFATTURE_SUPABASE_URL`
   - `RANDFATTURE_SUPABASE_SERVICE_KEY` (service role, **mai** nel browser)
   - `RANDFATTURE_SUPABASE_BUCKET=invoices`
4. Avvia l’app (`start.bat` o backend+frontend).
5. Primo accesso: PIN **Sviluppatore**.
6. Impostazioni → PIN per **Caricatore** (e altri utenti).
7. Login Caricatore → carica un PDF/XML di prova.
8. Login operatore → **Coda Storage** → Anteprima → Conferma.
9. (Opzionale) `scarica-modelli-ia.bat` per `qwen3:4b` + `nomic-embed-text`.

Senza `.env` Supabase l’app resta operativa con mirror locale `data/supabase_mirror/`.

## Flusso

1. **Sviluppatore** configura il PIN al primo avvio e assegna i PIN agli altri utenti (incluso `caricatore`).
2. **Caricatore** accede e vede solo *Carica fatture* → upload su Supabase Storage (o mirror locale).
3. All’upload viene calcolato lo **SHA-256**. Se esiste già in archivio → *Possibile duplicato*.
4. **Operatori** aprono *Coda Storage*, confrontano i doppioni, generano l’anteprima e confermano (o *Forza comunque*) l’import nel SQLite locale.

## Variabili `.env`

```env
RANDFATTURE_SUPABASE_URL=https://xxxx.supabase.co
RANDFATTURE_SUPABASE_SERVICE_KEY=eyJ...   # service role, solo sul PC
RANDFATTURE_SUPABASE_BUCKET=invoices
```

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
