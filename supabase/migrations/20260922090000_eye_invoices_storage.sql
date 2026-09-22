-- Eye Supremo · locazione fatture su progetto Supabase MultiHotel
-- Progetto: ooqlfldcrnkudhgjnied (Apice MultiHotel)
-- Applicare da Supabase SQL Editor (o CLI) con ruolo service/postgres.
--
-- Locazione file:
--   bucket: eye-invoices  (privato)
--   path:   apice/xml/YYYY/MM/<hash16>_<filename>
--           apice/pdf/YYYY/MM/<hash16>_<filename>
--
-- I ~20k metadati restano accessibili via RPC eye_central_invoice_page.
-- Questo bucket è la cassaforte dei blob XML/PDF originali.

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

-- Indice di locazione: collega hash/filename Eye central → path Storage
create table if not exists public.eye_invoice_files (
  id uuid primary key default gen_random_uuid(),
  source_hash text not null,
  source_filename text not null,
  storage_bucket text not null default 'eye-invoices',
  storage_path text not null,
  content_type text,
  size_bytes bigint,
  invoice_id uuid,
  uploaded_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (storage_bucket, storage_path),
  unique (source_hash)
);

create index if not exists eye_invoice_files_filename_idx
  on public.eye_invoice_files (source_filename);

create index if not exists eye_invoice_files_created_idx
  on public.eye_invoice_files (created_at desc);

alter table public.eye_invoice_files enable row level security;

revoke all on public.eye_invoice_files from anon, authenticated;
grant select, insert, update on public.eye_invoice_files to service_role;

-- Storage: solo service_role (PC Eye Supremo con service key). Niente accesso anon.
drop policy if exists eye_invoices_service_all on storage.objects;
create policy eye_invoices_service_all
on storage.objects
for all
to service_role
using (bucket_id = 'eye-invoices')
with check (bucket_id = 'eye-invoices');

comment on table public.eye_invoice_files is
  'Locazione blob fatture Eye Supremo nel bucket eye-invoices (XML/PDF).';
