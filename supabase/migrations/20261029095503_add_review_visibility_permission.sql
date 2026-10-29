begin;

alter table eye_supremo.eye_central_users
  add column if not exists can_view_reviews boolean not null default true;

comment on column eye_supremo.eye_central_users.can_view_reviews is
  'Consente al profilo di leggere, sincronizzare e analizzare le recensioni.';

create or replace function eye_supremo.eye_review_access_allowed(p_username text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from eye_supremo.eye_central_users u
    where u.username = lower(trim(p_username))
      and u.active
      and u.can_view_reviews
  );
$$;

revoke all on function eye_supremo.eye_review_access_allowed(text) from public, anon, authenticated;

create or replace function public.eye_central_review_page(
  p_username text,
  p_pin text,
  p_offset integer default 0,
  p_limit integer default 500
)
returns jsonb
language plpgsql
security definer
set search_path to 'public', 'extensions'
as $$
declare
  result jsonb;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;
  if not eye_supremo.eye_review_access_allowed(p_username) then
    raise exception 'Accesso alle recensioni non autorizzato';
  end if;

  select coalesce(jsonb_agg(to_jsonb(x) order by x.review_date desc, x.sync_uuid), '[]'::jsonb)
  into result
  from (
    select sync_uuid, hotel_code, review_date, source, author, rating, room_code, text
    from eye_supremo.eye_central_reviews
    order by review_date desc, sync_uuid
    offset greatest(p_offset, 0)
    limit least(greatest(p_limit, 1), 500)
  ) x;

  return jsonb_build_object(
    'items', result,
    'offset', p_offset,
    'limit', p_limit,
    'total', (select count(*) from eye_supremo.eye_central_reviews)
  );
end;
$$;

create or replace function public.eye_central_review_page(
  p_username text,
  p_pin text,
  p_offset integer default 0,
  p_limit integer default 500,
  p_since timestamp with time zone default null
)
returns jsonb
language plpgsql
security definer
set search_path to 'public', 'extensions'
as $$
declare
  result jsonb;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;
  if not eye_supremo.eye_review_access_allowed(p_username) then
    raise exception 'Accesso alle recensioni non autorizzato';
  end if;

  select coalesce(jsonb_agg(to_jsonb(x) order by x.review_date desc, x.sync_uuid), '[]'::jsonb)
  into result
  from (
    select sync_uuid, hotel_code, review_date, source, author, rating, room_code, text, updated_at
    from eye_supremo.eye_central_reviews
    where p_since is null or updated_at > p_since
    order by review_date desc, sync_uuid
    offset greatest(p_offset, 0)
    limit least(greatest(p_limit, 1), 500)
  ) x;

  return jsonb_build_object(
    'items', result,
    'offset', p_offset,
    'limit', p_limit,
    'total', (select count(*) from eye_supremo.eye_central_reviews)
  );
end;
$$;

create or replace function public.eye_central_review_upsert(
  p_username text,
  p_pin text,
  p_review jsonb
)
returns jsonb
language plpgsql
security definer
set search_path to 'public', 'extensions'
as $$
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then
    raise exception 'Credenziali non valide';
  end if;
  if not eye_supremo.eye_review_access_allowed(p_username) then
    raise exception 'Accesso alle recensioni non autorizzato';
  end if;

  insert into eye_supremo.eye_central_reviews(
    sync_uuid, hotel_code, review_date, source, author, rating, room_code, text, updated_at
  ) values (
    p_review->>'sync_uuid',
    p_review->>'hotel_code',
    (p_review->>'review_date')::date,
    p_review->>'source',
    p_review->>'author',
    (p_review->>'rating')::numeric,
    p_review->>'room_code',
    p_review->>'text',
    now()
  )
  on conflict(sync_uuid) do update set
    hotel_code = excluded.hotel_code,
    review_date = excluded.review_date,
    source = excluded.source,
    author = excluded.author,
    rating = excluded.rating,
    room_code = excluded.room_code,
    text = excluded.text,
    updated_at = now();

  return jsonb_build_object('sync_uuid', p_review->>'sync_uuid');
end;
$$;

revoke all on function public.eye_central_review_page(text,text,integer,integer) from public;
revoke all on function public.eye_central_review_page(text,text,integer,integer,timestamptz) from public;
revoke all on function public.eye_central_review_upsert(text,text,jsonb) from public;

grant execute on function public.eye_central_review_page(text,text,integer,integer) to anon, authenticated;
grant execute on function public.eye_central_review_page(text,text,integer,integer,timestamptz) to anon, authenticated;
grant execute on function public.eye_central_review_upsert(text,text,jsonb) to anon, authenticated;

notify pgrst, 'reload schema';
commit;
