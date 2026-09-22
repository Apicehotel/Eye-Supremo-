# PC-only · Supabase Storage (solo file)

Momentaneamente Eye/RandFatture resta sul **PC**. Supabase non è il database fatture: è solo lo **Storage** dei file caricati.

## Flusso

1. **Sviluppatore** configura il PIN al primo avvio e assegna i PIN agli altri utenti (incluso `caricatore`).
2. **Caricatore** accede e vede solo *Carica fatture* → upload su Supabase Storage (o mirror locale se `.env` assente).
3. All’upload viene calcolato lo **SHA-256**. Se esiste già in archivio → stato `possible_duplicate`.
4. **Operatori** aprono *Coda Storage*, confrontano i doppioni, generano l’anteprima e confermano (o forzano) l’import nel SQLite locale.

## Variabili `.env`

```env
RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co
RANDFATTURE_SUPABASE_SERVICE_KEY=eyJ...   # service role, solo sul PC
RANDFATTURE_SUPABASE_ANON_KEY=           # opzionale, per catalogo senza service key
RANDFATTURE_SUPABASE_BUCKET=eye-invoices
RANDFATTURE_SUPABASE_STORAGE_ROOT=invoices
RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore
RANDFATTURE_SUPABASE_CENTRAL_PIN=        # PIN MultiHotel (RPC eye_central_invoice_page)
```

Senza queste variabili l’app usa `data/supabase_mirror/` (utile in sviluppo/test) con gli stessi path relativi.

## Bucket Supabase

Progetto MultiHotel (`ooqlfldcrnkudhgjnied`). Creare bucket + indice eseguendo
`supabase/migrations/20260922090000_eye_invoices_storage.sql` (vedi `docs/SUPABASE_INVOICES.md`).

Path content-addressable: `invoices/{xml|pdf|doc}/{hh}/{sha256}{ext}`.

La service key resta nel backend locale: non esporla nel frontend.

In app: **Catalogo centrale** elenca i metadati MultiHotel (~20k) senza scaricare i blob.

## Ruoli

| Username     | Ruolo      | Capacità |
|--------------|------------|----------|
| sviluppatore | developer  | tutto + PIN utenti |
| supremo      | supremo    | operativo + coda |
| livello1–3   | level*     | operativo + coda |
| caricatore   | uploader   | solo upload file |

## IA consigliata (16 GB RAM)

`qwen3:4b` + `nomic-embed-text` via Ollama. Non obbligatori per carico/coda.
