-- Foglio ordini per fornitore condiviso tra i PC. Accesso solo via RPC con credenziali (RLS attiva, nessuna policy).
create table if not exists eye_supremo.eye_supplier_order_sheets (
  supplier_key text primary key,
  supplier_name text not null,
  filename text,
  payload jsonb not null,
  imported_at timestamptz not null default now(),
  imported_by text
);
alter table eye_supremo.eye_supplier_order_sheets enable row level security;

create or replace function public.eye_supplier_sheet_save(p_username text, p_pin text, p_supplier_key text, p_supplier_name text, p_filename text, p_payload jsonb)
returns jsonb language plpgsql security definer set search_path to 'public', 'extensions' as $function$
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if;
  insert into eye_supremo.eye_supplier_order_sheets(supplier_key, supplier_name, filename, payload, imported_at, imported_by)
  values (p_supplier_key, p_supplier_name, p_filename, p_payload, now(), p_username)
  on conflict (supplier_key) do update set supplier_name = excluded.supplier_name, filename = excluded.filename,
    payload = excluded.payload, imported_at = now(), imported_by = excluded.imported_by;
  return jsonb_build_object('ok', true);
end; $function$;

create or replace function public.eye_supplier_sheet_get(p_username text, p_pin text, p_supplier_key text)
returns jsonb language plpgsql security definer set search_path to 'public', 'extensions' as $function$
declare r eye_supremo.eye_supplier_order_sheets;
begin
  if not eye_supremo.eye_credentials_valid(p_username, p_pin) then raise exception 'Credenziali non valide'; end if;
  select * into r from eye_supremo.eye_supplier_order_sheets where supplier_key = p_supplier_key;
  if not found then return null; end if;
  return jsonb_build_object('supplier_name', r.supplier_name, 'filename', r.filename, 'imported_at', r.imported_at, 'imported_by', r.imported_by, 'data', r.payload);
end; $function$;

revoke all on function public.eye_supplier_sheet_save(text, text, text, text, text, jsonb) from public;
revoke all on function public.eye_supplier_sheet_get(text, text, text) from public;
grant execute on function public.eye_supplier_sheet_save(text, text, text, text, text, jsonb) to anon, authenticated;
grant execute on function public.eye_supplier_sheet_get(text, text, text) to anon, authenticated;
