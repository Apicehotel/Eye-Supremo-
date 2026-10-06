create table if not exists public.eye_central_reviews (
  sync_uuid text primary key,
  hotel_code text not null check (hotel_code in ('gio','choco','brigantino')),
  review_date date not null,
  source text,
  author text,
  rating numeric(4,2),
  room_code text,
  text text not null,
  updated_at timestamptz not null default now()
);
create index if not exists eye_central_reviews_hotel_date_idx on public.eye_central_reviews(hotel_code, review_date desc);
create index if not exists eye_central_reviews_text_idx on public.eye_central_reviews using gin(to_tsvector('simple', text));
alter table public.eye_central_reviews enable row level security;
revoke all on public.eye_central_reviews from anon, authenticated;
grant all on public.eye_central_reviews to service_role;

create or replace function public.eye_central_review_upsert(p_username text, p_pin text, p_review jsonb)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
begin
 if not exists (select 1 from public.eye_central_users where username=p_username and pin_hash=extensions.crypt(p_pin,pin_hash) and active=true and role in ('supremo','developer')) then raise exception 'Credenziali non valide'; end if;
 insert into public.eye_central_reviews(sync_uuid,hotel_code,review_date,source,author,rating,room_code,text,updated_at)
 values (p_review->>'sync_uuid',p_review->>'hotel_code',(p_review->>'review_date')::date,p_review->>'source',p_review->>'author',(p_review->>'rating')::numeric,p_review->>'room_code',p_review->>'text',now())
 on conflict (sync_uuid) do update set hotel_code=excluded.hotel_code,review_date=excluded.review_date,source=excluded.source,author=excluded.author,rating=excluded.rating,room_code=excluded.room_code,text=excluded.text,updated_at=now();
 return jsonb_build_object('sync_uuid',p_review->>'sync_uuid');
end; $$;
grant execute on function public.eye_central_review_upsert(text,text,jsonb) to anon, authenticated;

create or replace function public.eye_central_review_page(p_username text, p_pin text, p_offset integer default 0, p_limit integer default 500, p_since timestamptz default null)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare result jsonb;
begin
 if not exists (select 1 from public.eye_central_users where username=p_username and pin_hash=extensions.crypt(p_pin,pin_hash) and active=true and role in ('supremo','developer')) then raise exception 'Credenziali non valide'; end if;
 select coalesce(jsonb_agg(to_jsonb(x) order by x.review_date desc, x.sync_uuid), '[]'::jsonb) into result from (select sync_uuid,hotel_code,review_date,source,author,rating,room_code,text,updated_at from public.eye_central_reviews where p_since is null or updated_at > p_since order by review_date desc,sync_uuid offset greatest(p_offset,0) limit least(greatest(p_limit,1),500)) x;
 return jsonb_build_object('items',result,'offset',p_offset,'limit',p_limit,'total',(select count(*) from public.eye_central_reviews));
end; $$;
grant execute on function public.eye_central_review_page(text,text,integer,integer,timestamptz) to anon, authenticated;
