# Eye Supremo · spazio Supabase isolato

Stato applicato il 2026-10-02 sul progetto Supabase temporaneo condiviso `ooqlfldcrnkudhgjnied`.

## Confini

- **HotelGio**: non viene toccato da questa separazione.
- **MultiHotel / RandApp**: continua a usare lo schema `public`.
- **Eye Supremo**: dati centrali isolati nello schema privato `eye_supremo`.
- **Storage Eye**: bucket privato `eye-invoices`.

Lo schema `eye_supremo` non è esposto direttamente al Data API. Le Edge Function Eye usano `SUPABASE_DB_URL` e PostgreSQL diretto.

## Oggetti Eye spostati

- `eye_central_invoice_rows`
- `eye_central_invoices`
- `eye_central_product_catalog`
- `eye_central_products`
- `eye_central_reviews`
- `eye_central_suppliers`
- `eye_central_users`
- `eye_sync_memberships`
- `eye_sync_objects`
- view `eye_central_invoice_search`

Le RPC legacy `public.eye_*` restano temporaneamente come facciata di compatibilità e puntano allo schema `eye_supremo`.

## Compatibilità EXE

`public.eye_central_invoice_blobs` resta per ora una tabella fisica in `public` perché le installazioni Eye esistenti fanno ancora l'upsert REST diretto su quel path. È disponibile anche come view `eye_supremo.eye_central_invoice_blobs`.

Quando tutte le installazioni useranno il gateway per registrare i blob, anche questa ultima tabella potrà essere spostata nello schema Eye.

## Edge Function

- `eye-central-gateway`: PostgreSQL diretto, azioni `invoice_page`, `review_page`, ricerca e import fatture.
- `eye-supremo-sync`: verifica identità con Supabase Auth, poi legge/scrive `eye_supremo.eye_sync_*` via PostgreSQL diretto.

Questo evita di dipendere da PostgREST per il backend Eye e prepara la futura migrazione su PC/PostgreSQL locale senza cambiare il contratto applicativo.
