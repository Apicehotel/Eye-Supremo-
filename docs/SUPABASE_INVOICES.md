# Locazione fatture su Supabase (progetto MultiHotel)

## Progetto

| Campo | Valore |
|-------|--------|
| Progetto Supabase | **Apice MultiHotel** |
| Project ref | `ooqlfldcrnkudhgjnied` |
| URL | `https://ooqlfldcrnkudhgjnied.supabase.co` |
| Repo schema correlato | `Apicehotel/Apicehotel-Manutenzione` |
| Metadati già presenti | RPC `eye_central_invoice_page` → **~20.638** fatture |

## Locazione file (nuova)

| Campo | Valore |
|-------|--------|
| Bucket | `eye-invoices` (privato) |
| Path XML | `apice/xml/YYYY/MM/<hash16>_<filename>.xml` |
| Path PDF | `apice/pdf/YYYY/MM/<hash16>_<filename>.pdf` |
| Indice DB | tabella `public.eye_invoice_files` (hash → path) |

Esempio:

```text
eye-invoices/apice/xml/2026/07/30ed1ecb27af6bd9_IT03618500403_41sVr.xml
```

## Come creare la locazione

1. Apri Supabase → progetto MultiHotel → **SQL Editor**.
2. Esegui lo script:
   `supabase/migrations/20260922090000_eye_invoices_storage.sql`
3. Verifica in **Storage** che esista il bucket `eye-invoices`.

## Config Eye Supremo (PC)

`.env`:

```env
RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co
RANDFATTURE_SUPABASE_SERVICE_KEY=...   # service role, solo sul PC (upload blob)
RANDFATTURE_SUPABASE_ANON_KEY=...      # opzionale: basta per leggere il catalogo
RANDFATTURE_SUPABASE_BUCKET=eye-invoices
RANDFATTURE_SUPABASE_PATH_PREFIX=apice
RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore
RANDFATTURE_SUPABASE_CENTRAL_PIN=...   # PIN MultiHotel per RPC (non è il PIN locale Eye)
```

Senza service key l’app continua con mirror locale `data/supabase_mirror/` (stessi path relativi).
Con URL + chiave (service o anon) + PIN centrale, la pagina **Catalogo centrale** legge i ~20k metadati via `eye_central_invoice_page`.

All’upload su Supabase, Eye prova anche a registrare la riga in `eye_invoice_files` (richiede la migration).

## Separazione responsabilità

- **SQLite sul PC**: archivio operativo, prezzi, magazzino, conferma import.
- **Supabase `eye_central_*`**: elenco metadati centrali (~20k).
- **Supabase Storage `eye-invoices`**: blob XML/PDF originali.
- **GitHub**: solo codice, mai fatture reali.
