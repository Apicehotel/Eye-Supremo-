create table if not exists public.eye_central_suppliers (
  id uuid primary key default gen_random_uuid(),
  ragione_sociale text not null,
  partita_iva text,
  codice_fiscale text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (partita_iva),
  unique (ragione_sociale, partita_iva)
);

create table if not exists public.eye_central_invoices (
  id uuid primary key default gen_random_uuid(),
  source_hash text not null unique,
  source_filename text not null,
  supplier_id uuid not null references public.eye_central_suppliers(id),
  invoice_number text not null,
  invoice_date date not null,
  taxable numeric(14,2) not null default 0,
  vat numeric(14,2) not null default 0,
  total numeric(14,2) not null default 0,
  currency text not null default 'EUR',
  destination_hotel text check (destination_hotel in ('gio','choco','brigantino') or destination_hotel is null),
  extracted_text text,
  source_storage_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (supplier_id, invoice_number, invoice_date, total)
);

create table if not exists public.eye_central_products (
  id uuid primary key default gen_random_uuid(),
  canonical_name text not null unique,
  category text,
  brand text,
  code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.eye_central_invoice_rows (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.eye_central_invoices(id) on delete cascade,
  product_id uuid references public.eye_central_products(id),
  original_description text not null,
  normalized_description text not null,
  quantity numeric(14,4) not null default 1,
  original_unit text,
  normalized_unit text,
  unit_price numeric(14,4) not null default 0,
  line_total numeric(14,2) not null default 0,
  vat_rate numeric(6,2),
  normalized_price numeric(14,4),
  confidence numeric(4,3) not null default 1,
  analysis_status text not null default 'product' check (analysis_status in ('product','accounting_excluded','review')),
  exclusion_reason text,
  created_at timestamptz not null default now()
);

create index if not exists eye_central_invoices_date_idx on public.eye_central_invoices(invoice_date desc);
create index if not exists eye_central_invoices_supplier_idx on public.eye_central_invoices(supplier_id);
create index if not exists eye_central_rows_invoice_idx on public.eye_central_invoice_rows(invoice_id);
create index if not exists eye_central_rows_description_idx on public.eye_central_invoice_rows(normalized_description);
create index if not exists eye_central_products_name_idx on public.eye_central_products(canonical_name);

-- Paginated, authenticated read used by the local SQLite mirror.
drop function if exists public.eye_central_invoice_page(text,text,integer,integer);
create or replace function public.eye_central_invoice_page(p_username text, p_pin text, p_offset integer default 0, p_limit integer default 500, p_since timestamptz default null)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare result jsonb;
begin
  if not exists (select 1 from public.eye_central_users where username=p_username and pin_hash=extensions.crypt(p_pin,pin_hash) and active=true and role in ('supremo','developer')) then raise exception 'Credenziali non valide'; end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.invoice_date desc, x.id), '[]'::jsonb) into result
  from (select i.id,i.source_hash,i.source_filename,i.invoice_number,i.invoice_date,i.taxable,i.vat,i.total,i.currency,i.destination_hotel,s.ragione_sociale supplier_name
        from public.eye_central_invoices i join public.eye_central_suppliers s on s.id=i.supplier_id
        where p_since is null or i.updated_at > p_since
        order by i.invoice_date desc,i.id offset greatest(p_offset,0) limit least(greatest(p_limit,1),500)) x;
  return jsonb_build_object('items',result,'offset',p_offset,'limit',p_limit,'total',(select count(*) from public.eye_central_invoices));
end; $$;
grant execute on function public.eye_central_invoice_page(text,text,integer,integer,timestamptz) to anon, authenticated;

alter table public.eye_central_suppliers enable row level security;
alter table public.eye_central_invoices enable row level security;
alter table public.eye_central_products enable row level security;
alter table public.eye_central_invoice_rows enable row level security;

revoke all on public.eye_central_suppliers, public.eye_central_invoices, public.eye_central_products, public.eye_central_invoice_rows from anon, authenticated;
grant select, insert, update on public.eye_central_suppliers, public.eye_central_invoices, public.eye_central_products, public.eye_central_invoice_rows to service_role;

create or replace view public.eye_central_invoice_search with (security_invoker = true) as
select i.id, i.source_hash, i.source_filename, i.invoice_number, i.invoice_date,
       i.taxable, i.vat, i.total, i.currency, i.destination_hotel,
       s.ragione_sociale as supplier_name, r.original_description,
       r.normalized_description, r.quantity, r.unit_price, r.line_total,
       r.analysis_status
from public.eye_central_invoices i
join public.eye_central_suppliers s on s.id = i.supplier_id
join public.eye_central_invoice_rows r on r.invoice_id = i.id;
