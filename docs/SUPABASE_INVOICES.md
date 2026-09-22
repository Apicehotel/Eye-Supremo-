# Locazione fatture su Supabase (progetto MultiHotel)

## Mappa (struttura ottimale)

```text
MultiHotel (ooqlfldcrnkudhgjnied)
├── Metadati (già presenti)
│   ├── eye_central_invoices          ~20.638 intestazioni
│   ├── eye_central_invoice_rows      righe
│   └── RPC eye_central_invoice_page  lettura paginata (PIN)
│
└── Blob (nuovi — questa migration)
    ├── Storage bucket  eye-invoices   (privato, solo service_role)
    │   └── invoices/{xml|pdf|doc}/{hh}/{sha256}{ext}
    └── Tabella         eye_central_invoice_blobs
        └── PK = source_hash  → join 1:1 con i metadati
```

| Campo | Valore |
|-------|--------|
| Progetto | **Apice MultiHotel** · `ooqlfldcrnkudhgjnied` |
| URL | `https://ooqlfldcrnkudhgjnied.supabase.co` |
| Bucket | `eye-invoices` (privato) |
| Path | `invoices/{kind}/{hh}/{source_hash}{ext}` |
| Indice | `public.eye_central_invoice_blobs` |

Esempio:

```text
eye-invoices/invoices/xml/30/30ed1ecb27af6bd9757a864c3c51d0077942865462dbb16f431fd75c40c8f6a9.xml
```

Perché così:
- **content-addressable** → stesso file = stesso path → dedup con `x-upsert`
- **shard `{hh}`** → listing Storage più leggero con 20k+ oggetti
- **naming `eye_central_*`** → allineato a invoices/rows già in MultiHotel
- **niente data/filename nel path** → niente doppioni se si ricarica o si rinomina

## Come creare la locazione

1. Supabase → MultiHotel → **SQL Editor**
2. Esegui `supabase/migrations/20260922090000_eye_invoices_storage.sql`
3. Verifica bucket `eye-invoices` in **Storage**

## Config Eye Supremo (PC)

```env
RANDFATTURE_SUPABASE_URL=https://ooqlfldcrnkudhgjnied.supabase.co
RANDFATTURE_SUPABASE_SERVICE_KEY=...   # upload blob + indice
RANDFATTURE_SUPABASE_ANON_KEY=...      # opzionale: solo lettura catalogo
RANDFATTURE_SUPABASE_BUCKET=eye-invoices
RANDFATTURE_SUPABASE_STORAGE_ROOT=invoices
RANDFATTURE_SUPABASE_CENTRAL_USERNAME=sviluppatore
RANDFATTURE_SUPABASE_CENTRAL_PIN=...   # PIN MultiHotel (non PIN locale Eye)
```

- Senza service key → mirror locale `data/supabase_mirror/` (stessi path).
- URL + chiave + PIN → pagina **Catalogo centrale** (~20k metadati).
- All’upload Supabase → upsert su `eye_central_invoice_blobs`.

## Separazione responsabilità

| Dove | Cosa |
|------|------|
| SQLite PC | archivio operativo, prezzi, magazzino, conferma import |
| `eye_central_*` | metadati centrali + indice blob |
| Storage `eye-invoices` | XML/PDF originali |
| GitHub | solo codice |
