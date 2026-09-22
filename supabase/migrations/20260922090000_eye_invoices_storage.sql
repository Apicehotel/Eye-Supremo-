-- Eye Supremo · locazione blob fatture su MultiHotel (ooqlfldcrnkudhgjnied)
--
-- Allineata all'ecosistema già presente:
--   metadati  → public.eye_central_invoices (+ RPC eye_central_invoice_page)
--   righe     → public.eye_central_invoice_rows
--   blob      → Storage bucket eye-invoices + public.eye_central_invoice_blobs
--
-- Path content-addressable (stabile, dedup naturale con x-upsert):
--   invoices/{xml|pdf|doc}/{hh}/{source_hash}{ext}
--   es. invoices/xml/30/30ed1ecb27af6bd9….xml
--
-- Applicare da SQL Editor (service/postgres). Idempotente.

-- 1) Bucket privato ----------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'eye-invoices',
  'eye-invoices',
  false,
  31457280, -- 30 MB
  array[
    'application/xml',
    'text/xml',
    'application/pdf',
    'image/jpeg',
    'image/png',
    'application/octet-stream'
  ]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- 2) Indice blob (naming eye_central_* , PK = source_hash come i metadati) ---
-- Se esiste la vecchia bozza eye_invoice_files, la migriamo e la rimuoviamo.
create table if not exists public.eye_central_invoice_blobs (
  source_hash text primary key,
  source_filename text not null,
  kind text not null check (kind in ('xml', 'pdf', 'doc')),
  storage_bucket text not null default 'eye-invoices',
  storage_path text not null,
  content_type text,
  size_bytes bigint,
  invoice_id uuid,              -- opzionale: id in eye_central_invoices
  uploaded_by text,             -- username Eye PC (non auth.users)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint eye_central_invoice_blobs_path_uidx unique (storage_bucket, storage_path)
);

-- Migrazione soft dalla bozza precedente (se presente)
do $$
begin
  if to_regclass('public.eye_invoice_files') is not null then
    insert into public.eye_central_invoice_blobs as b (
      source_hash, source_filename, kind, storage_bucket, storage_path,
      content_type, size_bytes, invoice_id, uploaded_by, created_at, updated_at
    )
    select
      f.source_hash,
      f.source_filename,
      case
        when f.storage_path like '%/xml/%' or f.source_filename ilike '%.xml%' then 'xml'
        when f.storage_path like '%/pdf/%' or f.source_filename ilike '%.pdf' then 'pdf'
        else 'doc'
      end,
      coalesce(f.storage_bucket, 'eye-invoices'),
      f.storage_path,
      f.content_type,
      f.size_bytes,
      f.invoice_id,
      null,
      coalesce(f.created_at, now()),
      now()
    from public.eye_invoice_files f
    on conflict (source_hash) do update
      set source_filename = excluded.source_filename,
          kind = excluded.kind,
          storage_bucket = excluded.storage_bucket,
          storage_path = excluded.storage_path,
          content_type = excluded.content_type,
          size_bytes = excluded.size_bytes,
          invoice_id = coalesce(excluded.invoice_id, b.invoice_id),
          updated_at = now();
    drop table public.eye_invoice_files;
  end if;
end $$;

create index if not exists eye_central_invoice_blobs_filename_idx
  on public.eye_central_invoice_blobs (source_filename);

create index if not exists eye_central_invoice_blobs_kind_created_idx
  on public.eye_central_invoice_blobs (kind, created_at desc);

create index if not exists eye_central_invoice_blobs_invoice_id_idx
  on public.eye_central_invoice_blobs (invoice_id)
  where invoice_id is not null;

alter table public.eye_central_invoice_blobs enable row level security;

revoke all on public.eye_central_invoice_blobs from anon, authenticated;
grant select, insert, update on public.eye_central_invoice_blobs to service_role;

comment on table public.eye_central_invoice_blobs is
  'Locazione blob XML/PDF. Join metadati: eye_central_invoices.source_hash = eye_central_invoice_blobs.source_hash';

-- 3) Storage policies: solo service_role (PC Eye con service key) ------------
drop policy if exists eye_invoices_service_all on storage.objects;
create policy eye_invoices_service_all
on storage.objects
for all
to service_role
using (bucket_id = 'eye-invoices')
with check (bucket_id = 'eye-invoices');

-- Rimuovi eventuale policy della bozza se rinominata uguale
drop policy if exists eye_invoice_files_service_all on storage.objects;
