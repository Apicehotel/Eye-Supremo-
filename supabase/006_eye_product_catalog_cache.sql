create table if not exists public.eye_central_product_catalog (
  id text primary key,
  canonical_name text not null unique,
  category text,
  brand text,
  purchases bigint not null default 0,
  min_price numeric(14,4),
  avg_price numeric(14,4),
  max_price numeric(14,4),
  updated_at timestamptz not null default now()
);

create index if not exists eye_central_product_catalog_name_idx
  on public.eye_central_product_catalog using btree (canonical_name);

alter table public.eye_central_product_catalog enable row level security;
revoke all on public.eye_central_product_catalog from anon, authenticated;
grant select on public.eye_central_product_catalog to service_role;

create or replace function public.eye_refresh_product_catalog()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  truncate public.eye_central_product_catalog;
  insert into public.eye_central_product_catalog (id, canonical_name, category, brand, purchases, min_price, avg_price, max_price)
  with base as (
    select coalesce(nullif(p.canonical_name, ''), nullif(r.normalized_description, ''), r.original_description) as canonical_name,
      p.category, p.brand, coalesce(nullif(r.normalized_price, 0), nullif(r.unit_price, 0)) as normalized_price
    from public.eye_central_invoice_rows r
    left join public.eye_central_products p on p.id = r.product_id
    where r.analysis_status = 'product'
      and length(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) >= 3
      and trim(coalesce(nullif(r.normalized_description, ''), r.original_description)) !~ '^[-_.+=*]+$'
      and coalesce(r.quantity, 0) <> 0
      and coalesce(r.line_total, 0) <> 0
      and trim(coalesce(nullif(r.normalized_description, ''), r.original_description)) !~ '^([0-9]{1,2} ){2,3}[0-9]{2,4}$'
      and lower(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) !~ '(prestazione|riparazione|addebito|spese di incasso|firma digitale|manutenzione|controllo e riparazione|fornitura e montaggio|realizzazione|sostituzione|collegamento|lavori di manutenzione|contributo conai|regolamento ue|spese bollo|noleggio|canone|consulenza|assistenza|servizio|lavaggio|visita guidata|ore lavorate|camera (matrimoniale|quadrupla|tripla)|mezza pensione|commissione|imposta di soggiorno|tassa di soggiorno|soggiorno|alloggio|pernottamento|pensione|(^| )acconto( |$)|(^| )supplemento( |$)|(^| )riduzione( |$))'
      and lower(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) !~ '(^|[^a-z])(ddt[a-z0-9]*|documento di trasporto|fattura|nota di credito|totale|imponibile|iva|descrizione|quantita|quantità|prezzo|codice)([^a-z]|$)'
  )
  select md5(canonical_name), canonical_name, max(category), max(brand), count(*),
    min(nullif(normalized_price, 0)), avg(nullif(normalized_price, 0)), max(nullif(normalized_price, 0))
  from base group by canonical_name;
end;
$$;

revoke all on function public.eye_refresh_product_catalog() from public, anon, authenticated;
grant execute on function public.eye_refresh_product_catalog() to service_role;

select public.eye_refresh_product_catalog();
