-- Utenti centrali personali. Non modifica dati di MultiHotel o HotelGio.
-- Prerequisito: schema eye_supremo già attivato (vedi docs/SUPABASE_SPACE.md).
begin;
alter table eye_supremo.eye_central_users add column if not exists display_name text;
alter table eye_supremo.eye_central_users add column if not exists auth_version integer not null default 1;
update eye_supremo.eye_central_users set display_name=username where display_name is null;
alter table eye_supremo.eye_central_users alter column display_name set not null;
alter table eye_supremo.eye_central_users enable row level security;
revoke all on eye_supremo.eye_central_users from public, anon, authenticated;

create table if not exists eye_supremo.eye_identity_sessions (
  token_hash text primary key check (length(token_hash)=64),
  username text not null references eye_supremo.eye_central_users(username) on delete cascade,
  auth_version integer not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists eye_identity_sessions_user_idx on eye_supremo.eye_identity_sessions(username);
create index if not exists eye_identity_sessions_expiry_idx on eye_supremo.eye_identity_sessions(expires_at);
alter table eye_supremo.eye_identity_sessions enable row level security;
revoke all on eye_supremo.eye_identity_sessions from public, anon, authenticated;

create table if not exists eye_supremo.eye_identity_limits (
  key text primary key,
  window_start timestamptz not null,
  attempts integer not null
);
alter table eye_supremo.eye_identity_limits enable row level security;
revoke all on eye_supremo.eye_identity_limits from public, anon, authenticated;

-- Helper privato invocato dai wrapper SECURITY DEFINER già esistenti.
-- Non è una nuova RPC pubblica e non ha SECURITY DEFINER.
create or replace function eye_supremo.eye_credentials_valid(p_username text, p_credential text)
returns boolean language plpgsql stable security invoker set search_path='' as $$
begin
  if p_credential ~ '^eye1_[a-f0-9]{64}$' then
    return exists (
      select 1 from eye_supremo.eye_identity_sessions s
      join eye_supremo.eye_central_users u on u.username=s.username
      where u.username=p_username and u.active and u.role in ('developer','supremo')
        and s.auth_version=u.auth_version and s.expires_at>now()
        and s.token_hash=encode(extensions.digest(p_credential,'sha256'),'hex')
    );
  end if;
  -- Compatibilità temporanea con le installazioni precedenti.
  if p_credential !~ '^[0-9]{6,12}$' then return false; end if;
  return exists(select 1 from eye_supremo.eye_central_users u
    where u.username=p_username and u.active and u.role in ('developer','supremo')
      and u.pin_hash=extensions.crypt(p_credential,u.pin_hash));
end;
$$;
revoke all on function eye_supremo.eye_credentials_valid(text,text) from public, anon, authenticated;

-- Le RPC dati mantengono firma, risultati e controlli di ruolo; accettano anche
-- il token personale revocabile al posto del PIN. Definizioni dello stato attuale.
CREATE OR REPLACE FUNCTION public.eye_central_invoice_detail(p_username text, p_pin text, p_source_hash text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
declare result jsonb;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if;
  select jsonb_build_object('id', i.id, 'source_hash', i.source_hash, 'source_filename', i.source_filename, 'invoice_number', i.invoice_number, 'invoice_date', i.invoice_date, 'taxable', i.taxable, 'vat', i.vat, 'total', i.total, 'currency', i.currency, 'destination_hotel', i.destination_hotel, 'extracted_text', i.extracted_text, 'supplier_name', s.ragione_sociale, 'supplier_vat', s.partita_iva, 'rows', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'original_description', r.original_description, 'normalized_description', r.normalized_description, 'quantity', r.quantity, 'original_unit', r.original_unit, 'normalized_unit', r.normalized_unit, 'unit_price', r.unit_price, 'line_total', r.line_total, 'vat_rate', r.vat_rate, 'normalized_price', r.normalized_price, 'analysis_status', r.analysis_status, 'exclusion_reason', r.exclusion_reason) order by r.id) from eye_supremo.eye_central_invoice_rows r where r.invoice_id=i.id), '[]'::jsonb)) into result from eye_supremo.eye_central_invoices i join eye_supremo.eye_central_suppliers s on s.id=i.supplier_id where i.source_hash=p_source_hash;
  return coalesce(result, '{}'::jsonb);
end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_invoice_page(p_username text, p_pin text, p_offset integer DEFAULT 0, p_limit integer DEFAULT 500, p_since timestamp with time zone DEFAULT NULL::timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$ declare result jsonb; begin if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if; select coalesce(jsonb_agg(to_jsonb(x) order by x.invoice_date desc,x.id),'[]'::jsonb) into result from (select i.id,i.source_hash,i.source_filename,i.invoice_number,i.invoice_date,i.taxable,i.vat,i.total,i.currency,i.destination_hotel,s.ragione_sociale supplier_name,i.updated_at from eye_supremo.eye_central_invoices i join eye_supremo.eye_central_suppliers s on s.id=i.supplier_id where p_since is null or i.updated_at>p_since order by i.invoice_date desc,i.id offset greatest(p_offset,0) limit least(greatest(p_limit,1),500)) x; return jsonb_build_object('items',result,'offset',p_offset,'limit',p_limit,'total',(select count(*) from eye_supremo.eye_central_invoices)); end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_product_detail(p_username text, p_pin text, p_canonical_name text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;

  return (
    select jsonb_build_object(
      'product', to_jsonb(c),
      'history', coalesce((
        select jsonb_agg(to_jsonb(h) order by h.invoice_date desc, h.invoice_number)
        from (
          select i.invoice_number, i.invoice_date, s.ragione_sociale as supplier_name,
            r.quantity, r.original_unit, r.unit_price, r.normalized_price,
            r.normalized_unit, r.line_total, i.source_hash
          from eye_supremo.eye_central_invoice_rows r
          join eye_supremo.eye_central_invoices i on i.id = r.invoice_id
          join eye_supremo.eye_central_suppliers s on s.id = i.supplier_id
          left join eye_supremo.eye_central_products p on p.id = r.product_id
          where r.analysis_status = 'product'
            and coalesce(nullif(p.canonical_name, ''), nullif(r.normalized_description, ''), r.original_description) = p_canonical_name
        ) h
      ), '[]'::jsonb)
    )
    from eye_supremo.eye_central_product_catalog c
    where c.canonical_name = p_canonical_name
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION public.eye_central_product_page(p_username text, p_pin text, p_query text DEFAULT ''::text, p_limit integer DEFAULT 200)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;

  return (
    with grouped as (
      select
        id,
        canonical_name as nome_canonico,
        category as categoria,
        brand as marca,
        purchases,
        min_price,
        avg_price,
        max_price
      from eye_supremo.eye_central_product_catalog
      where
        (
          coalesce(p_query, '') = ''
          or canonical_name ilike '%' || p_query || '%'
          or coalesce(category, '') ilike '%' || p_query || '%'
          or coalesce(brand, '') ilike '%' || p_query || '%'
        )
    )
    select jsonb_build_object(
      'items', coalesce((select jsonb_agg(to_jsonb(x) order by x.nome_canonico) from (select * from grouped order by nome_canonico limit least(greatest(p_limit, 1), 500)) x), '[]'::jsonb),
      'total', (select count(*) from grouped)
    )
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION public.eye_central_product_summary(p_username text, p_pin text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;

  return jsonb_build_object(
    'product_rows', (
      select count(*)
      from eye_supremo.eye_central_product_catalog
    ),
    'distinct_products', (
      select count(distinct canonical_name)
      from eye_supremo.eye_central_product_catalog
    )
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION public.eye_central_review_page(p_username text, p_pin text, p_offset integer DEFAULT 0, p_limit integer DEFAULT 500)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$ declare result jsonb; begin if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if; select coalesce(jsonb_agg(to_jsonb(x) order by x.review_date desc,x.sync_uuid),'[]'::jsonb) into result from (select sync_uuid,hotel_code,review_date,source,author,rating,room_code,text from eye_supremo.eye_central_reviews order by review_date desc,sync_uuid offset greatest(p_offset,0) limit least(greatest(p_limit,1),500)) x; return jsonb_build_object('items',result,'offset',p_offset,'limit',p_limit,'total',(select count(*) from eye_supremo.eye_central_reviews)); end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_review_page(p_username text, p_pin text, p_offset integer DEFAULT 0, p_limit integer DEFAULT 500, p_since timestamp with time zone DEFAULT NULL::timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$ declare result jsonb; begin if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if; select coalesce(jsonb_agg(to_jsonb(x) order by x.review_date desc,x.sync_uuid),'[]'::jsonb) into result from (select sync_uuid,hotel_code,review_date,source,author,rating,room_code,text,updated_at from eye_supremo.eye_central_reviews where p_since is null or updated_at>p_since order by review_date desc,sync_uuid offset greatest(p_offset,0) limit least(greatest(p_limit,1),500)) x; return jsonb_build_object('items',result,'offset',p_offset,'limit',p_limit,'total',(select count(*) from eye_supremo.eye_central_reviews)); end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_review_upsert(p_username text, p_pin text, p_review jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$ begin if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if; insert into eye_supremo.eye_central_reviews(sync_uuid,hotel_code,review_date,source,author,rating,room_code,text,updated_at) values((p_review->>'sync_uuid'),p_review->>'hotel_code',(p_review->>'review_date')::date,p_review->>'source',p_review->>'author',(p_review->>'rating')::numeric,p_review->>'room_code',p_review->>'text',now()) on conflict(sync_uuid) do update set hotel_code=excluded.hotel_code,review_date=excluded.review_date,source=excluded.source,author=excluded.author,rating=excluded.rating,room_code=excluded.room_code,text=excluded.text,updated_at=now(); return jsonb_build_object('sync_uuid',p_review->>'sync_uuid'); end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_supplier_detail(p_username text, p_pin text, p_supplier_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
declare supplier_data jsonb; invoice_data jsonb; category_data jsonb; fuel numeric;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if;
  select to_jsonb(x) into supplier_data from (
    select s.id, s.ragione_sociale, s.partita_iva, s.codice_fiscale,
           null::text as indirizzo, null::text as email, null::text as telefono,
           count(i.id)::integer as invoice_count,
           coalesce(sum(case when i.total >= 0 then i.total else 0 end),0) as total_spent,
           coalesce(sum(case when i.total < 0 then i.total else 0 end),0) as credit_total,
           max(i.invoice_date) as last_invoice_date
    from eye_supremo.eye_central_suppliers s left join eye_supremo.eye_central_invoices i on i.supplier_id=s.id
    where s.id=p_supplier_id group by s.id
  ) x;
  if supplier_data is null then return jsonb_build_object('supplier', null, 'invoices','[]'::jsonb,'categories','[]'::jsonb,'fuel_total',0); end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.invoice_date desc, x.invoice_number), '[]'::jsonb) into invoice_data from (
    select i.id, i.source_hash, i.source_filename, i.invoice_number, i.invoice_date, i.taxable, i.vat, i.total, i.currency, i.destination_hotel
    from eye_supremo.eye_central_invoices i where i.supplier_id=p_supplier_id order by i.invoice_date desc, i.invoice_number limit 100
  ) x;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.total desc), '[]'::jsonb) into category_data from (
    select r.normalized_description as description, count(*)::integer as purchases,
           coalesce(sum(r.line_total),0) as total,
           left(string_agg(distinct i.invoice_number, ', ' order by i.invoice_number), 180) as invoice_references
    from eye_supremo.eye_central_invoice_rows r join eye_supremo.eye_central_invoices i on i.id=r.invoice_id
    where i.supplier_id=p_supplier_id and r.analysis_status <> 'accounting_excluded'
    group by r.normalized_description order by total desc limit 30
  ) x;
  select coalesce(sum(r.line_total),0) into fuel from eye_supremo.eye_central_invoice_rows r join eye_supremo.eye_central_invoices i on i.id=r.invoice_id
   where i.supplier_id=p_supplier_id and r.analysis_status <> 'accounting_excluded'
     and r.normalized_description ~* '(carburant|benzina|diesel|gasolio|metano|gpl)';
  return jsonb_build_object('supplier',supplier_data,'invoices',invoice_data,'categories',category_data,'fuel_total',fuel);
end; $function$
;

CREATE OR REPLACE FUNCTION public.eye_central_supplier_page(p_username text, p_pin text, p_query text DEFAULT ''::text, p_limit integer DEFAULT 2000)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
declare result jsonb;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.ragione_sociale), '[]'::jsonb) into result
  from (
    select s.id, s.ragione_sociale, s.partita_iva, s.codice_fiscale,
           count(i.id)::integer as invoice_count,
           coalesce(sum(case when i.total >= 0 then i.total else 0 end),0) as total_spent,
           coalesce(sum(case when i.total < 0 then i.total else 0 end),0) as credit_total,
           max(i.invoice_date) as last_invoice_date
    from eye_supremo.eye_central_suppliers s
    left join eye_supremo.eye_central_invoices i on i.supplier_id=s.id
    where coalesce(p_query,'') = ''
       or s.ragione_sociale ilike '%' || p_query || '%'
       or coalesce(s.partita_iva,'') ilike '%' || p_query || '%'
       or coalesce(s.codice_fiscale,'') ilike '%' || p_query || '%'
    group by s.id
    order by s.ragione_sociale
    limit least(greatest(coalesce(p_limit,2000),1),2000)
  ) x;
  return jsonb_build_object('items', result, 'total', (select count(*) from eye_supremo.eye_central_suppliers s where coalesce(p_query,'') = '' or s.ragione_sociale ilike '%' || p_query || '%' or coalesce(s.partita_iva,'') ilike '%' || p_query || '%' or coalesce(s.codice_fiscale,'') ilike '%' || p_query || '%'));
end; $function$
;

-- Mantieni i grant espliciti, senza EXECUTE ereditato da PUBLIC.
revoke all on function public.eye_central_invoice_page(text,text,integer,integer,timestamptz) from public;
revoke all on function public.eye_central_invoice_detail(text,text,text) from public;
revoke all on function public.eye_central_review_page(text,text,integer,integer,timestamptz) from public;
revoke all on function public.eye_central_review_upsert(text,text,jsonb) from public;
revoke all on function public.eye_central_product_summary(text,text) from public;
revoke all on function public.eye_central_product_page(text,text,text,integer) from public;
revoke all on function public.eye_central_product_detail(text,text,text) from public;
revoke all on function public.eye_central_supplier_page(text,text,text,integer) from public;
revoke all on function public.eye_central_supplier_detail(text,text,uuid) from public;
revoke all on function public.eye_central_review_page(text,text,integer,integer) from public;
grant execute on function public.eye_central_invoice_page(text,text,integer,integer,timestamptz),
 public.eye_central_invoice_detail(text,text,text),
 public.eye_central_review_page(text,text,integer,integer,timestamptz),
 public.eye_central_review_page(text,text,integer,integer),
 public.eye_central_review_upsert(text,text,jsonb),
 public.eye_central_product_summary(text,text),
 public.eye_central_product_page(text,text,text,integer),
 public.eye_central_product_detail(text,text,text),
 public.eye_central_supplier_page(text,text,text,integer),
 public.eye_central_supplier_detail(text,text,uuid) to anon, authenticated;
notify pgrst, 'reload schema';
commit;
