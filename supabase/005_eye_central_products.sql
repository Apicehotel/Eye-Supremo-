-- Paginated central product catalogue for the Products screen.
drop function if exists public.eye_central_product_page(text, text, text, integer);

create or replace function public.eye_central_product_page(
  p_username text,
  p_pin text,
  p_query text default '',
  p_limit integer default 200
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
      from public.eye_central_product_catalog
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
$$;

grant execute on function public.eye_central_product_page(text, text, text, integer) to anon, authenticated;
