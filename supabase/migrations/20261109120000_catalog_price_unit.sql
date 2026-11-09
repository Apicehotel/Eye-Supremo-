-- Catalogo prodotti: prezzi normalizzati (€/kg, €/l, €/pz) con la loro unità (price_unit).
-- eye_refresh_product_catalog: se un prodotto ha righe normalizzate, min/avg/max si calcolano solo su quelle
-- e price_unit è l'unità più frequente; altrimenti prezzo grezzo e price_unit nullo.
-- eye_central_product_page restituisce anche price_unit. Applicata a produzione su richiesta esplicita dell'utente.
create table if not exists eye_supremo.eye_product_page_def_backup_20261109 as
  select now() as backed_up_at,
         pg_get_functiondef('public.eye_central_product_page(text,text,text,integer)'::regprocedure) as definition,
         pg_get_functiondef('public.eye_refresh_product_catalog()'::regprocedure) as catalog_definition;
alter table eye_supremo.eye_product_page_def_backup_20261109 enable row level security;
alter table eye_supremo.eye_central_product_catalog add column if not exists price_unit text;

CREATE OR REPLACE FUNCTION public.eye_refresh_product_catalog()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions'
AS $function$
begin
  truncate eye_supremo.eye_central_product_catalog;
  insert into eye_supremo.eye_central_product_catalog (id, canonical_name, category, brand, purchases, min_price, avg_price, max_price, price_unit)
  with base as (
    select coalesce(nullif(p.canonical_name, ''), nullif(r.normalized_description, ''), r.original_description) as canonical_name,
      p.category, p.brand, coalesce(nullif(r.normalized_price, 0), nullif(r.unit_price, 0)) as normalized_price,
      (r.normalized_price is not null and r.normalized_price <> 0) as is_norm,
      r.normalized_unit as price_unit
    from eye_supremo.eye_central_invoice_rows r
    left join eye_supremo.eye_central_products p on p.id = r.product_id
    where r.analysis_status = 'product'
      and length(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) >= 3
      and trim(coalesce(nullif(r.normalized_description, ''), r.original_description)) !~ '^[-_.+=*]+$'
      and coalesce(r.quantity, 0) <> 0
      and coalesce(r.line_total, 0) > 0
      and trim(coalesce(nullif(r.normalized_description, ''), r.original_description)) !~ '^([0-9]{1,2} ){2,3}[0-9]{2,4}$'
      and lower(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) !~ '(carburante|gasolio|benzina|diesel|accis[ae]|trasporto|spedizion|corriere|sconto|abbuono|omaggio|spese bollo|imposta di bollo|cauzione|vuoto a rendere|epal|imballo|rettifica|storno|accredito|prestazione|riparazione|addebito|spese di incasso|firma digitale|manutenzione|controllo e riparazione|fornitura e montaggio|realizzazione|sostituzione|collegamento|lavori di manutenzione|contributo conai|regolamento ue|spese bollo|noleggio|canone|consulenza|assistenza|servizio|lavaggio|visita guidata|ore lavorate|camera (matrimoniale|quadrupla|tripla)|mezza pensione|commissione|imposta di soggiorno|tassa di soggiorno|soggiorno|alloggio|pernottamento|pensione|(^| )acconto( |$)|(^| )supplemento( |$)|(^| )riduzione( |$))'
      and lower(trim(coalesce(nullif(r.normalized_description, ''), r.original_description))) !~ '(^|[^a-z])(ddt[a-z0-9]*|documento di trasporto|fattura|nota di credito|totale|imponibile|iva|descrizione|quantita|quantità|prezzo|codice)([^a-z]|$)'
  ), flagged as (
    select base.*, bool_or(is_norm) over (partition by canonical_name) as has_norm from base
  )
  select md5(canonical_name), canonical_name, max(category), max(brand), count(*),
    min(nullif(normalized_price, 0)), avg(nullif(normalized_price, 0)), max(nullif(normalized_price, 0)),
    mode() within group (order by price_unit) filter (where is_norm)
  from flagged
  where (not has_norm or is_norm)
  group by canonical_name;
end;
$function$;

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
        max_price,
        price_unit
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
$function$;
