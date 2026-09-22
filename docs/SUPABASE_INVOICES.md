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
RANDFATTURE_SUPABASE_SERVICE_KEY=...   # service role, solo sul PC
RANDFATTURE_SUPABASE_BUCKET=eye-invoices
RANDFATTURE_SUPABASE_PATH_PREFIX=apice
```

Senza service key l’app continua con mirror locale `data/supabase_mirror/` (stessi path relativi).

## Separazione responsabilità

- **SQLite sul PC**: archivio operativo, prezzi, magazzino, conferma import.
- **Supabase `eye_central_*`**: elenco metadati centrali (~20k).
- **Supabase Storage `eye-invoices`**: blob XML/PDF originali.
- **GitHub**: solo codice, mai fatture reali.
