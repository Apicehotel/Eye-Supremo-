-- Central supplier directory and drill-down for the Suppliers screen.
drop function if exists public.eye_central_supplier_page(text,text,text,integer);
create or replace function public.eye_central_supplier_page(p_username text, p_pin text, p_query text default '', p_limit integer default 200)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare result jsonb;
begin
  if not exists (select 1 from public.eye_central_users where username=p_username and pin_hash=extensions.crypt(p_pin,pin_hash) and active=true and role in ('supremo','developer')) then raise exception 'Credenziali non valide'; end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.ragione_sociale), '[]'::jsonb) into result
  from (
    select s.id, s.ragione_sociale, s.partita_iva, s.codice_fiscale,
           count(i.id)::integer as invoice_count,
           coalesce(sum(case when i.total >= 0 then i.total else 0 end),0) as total_spent,
           coalesce(sum(case when i.total < 0 then i.total else 0 end),0) as credit_total,
           max(i.invoice_date) as last_invoice_date
    from public.eye_central_suppliers s
    left join public.eye_central_invoices i on i.supplier_id=s.id
    where coalesce(p_query,'') = ''
       or s.ragione_sociale ilike '%' || p_query || '%'
       or coalesce(s.partita_iva,'') ilike '%' || p_query || '%'
       or coalesce(s.codice_fiscale,'') ilike '%' || p_query || '%'
    group by s.id
    order by s.ragione_sociale
    limit least(greatest(coalesce(p_limit,200),1),2000)
  ) x;
  return jsonb_build_object('items', result, 'total', (select count(*) from public.eye_central_suppliers s where coalesce(p_query,'') = '' or s.ragione_sociale ilike '%' || p_query || '%' or coalesce(s.partita_iva,'') ilike '%' || p_query || '%' or coalesce(s.codice_fiscale,'') ilike '%' || p_query || '%'));
end; $$;
grant execute on function public.eye_central_supplier_page(text,text,text,integer) to anon, authenticated;

drop function if exists public.eye_central_supplier_detail(text,text,uuid);
create or replace function public.eye_central_supplier_detail(p_username text, p_pin text, p_supplier_id uuid)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare supplier_data jsonb; invoice_data jsonb; category_data jsonb; fuel numeric;
begin
  if not exists (select 1 from public.eye_central_users where username=p_username and pin_hash=extensions.crypt(p_pin,pin_hash) and active=true and role in ('supremo','developer')) then raise exception 'Credenziali non valide'; end if;
  select to_jsonb(x) into supplier_data from (
    select s.id, s.ragione_sociale, s.partita_iva, s.codice_fiscale,
           null::text as indirizzo, null::text as email, null::text as telefono,
           count(i.id)::integer as invoice_count,
           coalesce(sum(case when i.total >= 0 then i.total else 0 end),0) as total_spent,
           coalesce(sum(case when i.total < 0 then i.total else 0 end),0) as credit_total,
           max(i.invoice_date) as last_invoice_date
    from public.eye_central_suppliers s left join public.eye_central_invoices i on i.supplier_id=s.id
    where s.id=p_supplier_id group by s.id
  ) x;
  if supplier_data is null then return jsonb_build_object('supplier', null, 'invoices','[]'::jsonb,'categories','[]'::jsonb,'fuel_total',0); end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.invoice_date desc, x.invoice_number), '[]'::jsonb) into invoice_data from (
    select i.id, i.source_hash, i.source_filename, i.invoice_number, i.invoice_date, i.taxable, i.vat, i.total, i.currency, i.destination_hotel
    from public.eye_central_invoices i where i.supplier_id=p_supplier_id order by i.invoice_date desc, i.invoice_number limit 100
  ) x;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.total desc), '[]'::jsonb) into category_data from (
    select r.normalized_description as description, count(*)::integer as purchases,
           coalesce(sum(r.line_total),0) as total,
           left(string_agg(distinct i.invoice_number, ', ' order by i.invoice_number), 180) as invoice_references
    from public.eye_central_invoice_rows r join public.eye_central_invoices i on i.id=r.invoice_id
    where i.supplier_id=p_supplier_id and r.analysis_status <> 'accounting_excluded'
    group by r.normalized_description order by total desc limit 30
  ) x;
  select coalesce(sum(r.line_total),0) into fuel from public.eye_central_invoice_rows r join public.eye_central_invoices i on i.id=r.invoice_id
   where i.supplier_id=p_supplier_id and r.analysis_status <> 'accounting_excluded'
     and r.normalized_description ~* '(carburant|benzina|diesel|gasolio|metano|gpl)';
  return jsonb_build_object('supplier',supplier_data,'invoices',invoice_data,'categories',category_data,'fuel_total',fuel);
end; $$;
grant execute on function public.eye_central_supplier_detail(text,text,uuid) to anon, authenticated;
