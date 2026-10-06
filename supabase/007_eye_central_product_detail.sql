drop function if exists public.eye_central_product_detail(text, text, text);

create or replace function public.eye_central_product_detail(
  p_username text,
  p_pin text,
  p_canonical_name text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if not exists (
    select 1 from public.eye_central_users
    where username = p_username
      and pin_hash = extensions.crypt(p_pin, pin_hash)
      and active = true
      and role in ('supremo', 'developer')
  ) then
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
          from public.eye_central_invoice_rows r
          join public.eye_central_invoices i on i.id = r.invoice_id
          join public.eye_central_suppliers s on s.id = i.supplier_id
          left join public.eye_central_products p on p.id = r.product_id
          where r.analysis_status = 'product'
            and coalesce(nullif(p.canonical_name, ''), nullif(r.normalized_description, ''), r.original_description) = p_canonical_name
        ) h
      ), '[]'::jsonb)
    )
    from public.eye_central_product_catalog c
    where c.canonical_name = p_canonical_name
  );
end;
$$;

grant execute on function public.eye_central_product_detail(text, text, text) to anon, authenticated;
