-- Dashboard KPI: product rows and distinct product descriptions in the central invoice archive.
-- The function follows the same restricted Supabase access pattern as the other central RPCs.
drop function if exists public.eye_central_product_summary(text, text);

create or replace function public.eye_central_product_summary(
  p_username text,
  p_pin text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if not exists (
    select 1
    from public.eye_central_users
    where username = p_username
      and pin_hash = extensions.crypt(p_pin, pin_hash)
      and active = true
      and role in ('supremo', 'developer')
  ) then
    raise exception 'Credenziali non valide';
  end if;

  return jsonb_build_object(
    'product_rows', (
      select count(*)
      from public.eye_central_product_catalog
    ),
    'distinct_products', (
      select count(distinct canonical_name)
      from public.eye_central_product_catalog
    )
  );
end;
$$;

grant execute on function public.eye_central_product_summary(text, text) to anon, authenticated;
