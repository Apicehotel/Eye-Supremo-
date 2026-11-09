-- Prezzi normalizzati (€/kg, €/l, €/pz) sulle righe fattura del centrale.
--
-- Le funzioni qui sotto replicano `backend/app/normalization.py` (normalize_row_price / parse_pack):
-- se cambiano le regole in Python vanno aggiornate anche qui (e viceversa).
-- Le descrizioni originali non vengono mai modificate. Il ricalcolo scrive solo
-- normalized_unit / normalized_price, e solo dove normalized_price è ancora NULL.
--
-- Prima del ricalcolo i valori sono stati copiati in
-- eye_supremo.eye_central_invoice_rows_backup_20261109 (RLS attiva, solo service role).
-- Rollback: update eye_supremo.eye_central_invoice_rows r
--             set normalized_unit = b.normalized_unit, normalized_price = b.normalized_price
--             from eye_supremo.eye_central_invoice_rows_backup_20261109 b where b.id = r.id;
-- Ricalcolo (eseguito a blocchi per prefisso dell'id, poi eye_refresh_product_catalog()):
--   update eye_supremo.eye_central_invoice_rows r
--      set normalized_unit = n.o_unit, normalized_price = n.o_price
--     from (select id, (eye_supremo.eye_normalize_price(unit_price, quantity, original_unit, original_description)).*
--             from eye_supremo.eye_central_invoice_rows
--            where normalized_price is null and analysis_status = 'product' and id::text like '0%') n
--    where n.id = r.id and n.o_price is not null;

create or replace function eye_supremo.eye_unit_base_factor(
  p_unit text, out o_base text, out o_factor numeric, out o_kind text)
language plpgsql
immutable
set search_path = pg_catalog
as $$
declare
  k text;
begin
  o_factor := 1;
  if p_unit is null or p_unit = '' then
    o_base := null; o_kind := 'none'; return;
  end if;
  k := replace(replace(lower(btrim(p_unit)), 'mq', 'm2'), 'mc', 'm3');
  case k
    when 'kg', 'kg.', 'k.', 'kgm', 'kilo', 'kili', 'chilo', 'chili', 'kilogrammi', 'kilogrammo' then
      o_base := 'kg'; o_kind := 'kgl';
    when 'g', 'gr', 'grammo', 'grammi' then
      o_base := 'kg'; o_factor := 0.001; o_kind := 'kgl';
    when 'hg', 'etto', 'etti' then
      o_base := 'kg'; o_factor := 0.1; o_kind := 'kgl';
    when 'l', 'lt', 'lit', 'ltr', 'litro', 'litri' then
      o_base := 'l'; o_kind := 'kgl';
    when 'ml' then
      o_base := 'l'; o_factor := 0.001; o_kind := 'kgl';
    when 'cl' then
      o_base := 'l'; o_factor := 0.01; o_kind := 'kgl';
    when 'dl' then
      o_base := 'l'; o_factor := 0.1; o_kind := 'kgl';
    when 'pz', 'pezzo', 'pezzi', 'pcs', 'pc', 'n', 'n.', 'nr', 'num', 'numero', 'un', 'cad', 'cadauna', 'cadauno' then
      o_base := 'pz'; o_kind := 'piece';
    when 'conf', 'confezione', 'ct', 'cartone', 'cartoni', 'cf', 'sc', 'cs', 'cas', 'cassa', 'con', 'cu', 'bt',
         'pacco', 'sa', 'bs', 'busta', 'sacco', 'rn' then
      o_base := 'confezione'; o_kind := 'pack';
    when 'scatola' then
      o_base := 'scatola'; o_kind := 'pack';
    else
      o_base := k; o_kind := 'other';
  end case;
end;
$$;

create or replace function eye_supremo.eye_valid_count(p_text text)
returns integer
language sql
immutable
set search_path = pg_catalog
as $$
  select case when p_text ~ '^[0-9]{1,6}$' and p_text::integer between 1 and 100000 then p_text::integer end
$$;

create or replace function eye_supremo.eye_normalize_price(
  p_price numeric, p_qty numeric, p_unit text, p_desc text,
  out o_unit text, out o_price numeric)
language plpgsql
immutable
set search_path = pg_catalog
as $$
declare
  c_mv constant text := 'kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|lit|l|ml|cl|dl';
  c_count_words constant text := 'pz|pezzi|pcs|fette|filtri|buste|bustine|capsule|cialde|rotoli|fogli|porzioni|bottiglie|lattine|pacchi|barrette';
  re_num_unit constant text := '(?<![0-9])(\d+(?:[.,]\d+)?|0\s\d{1,3})\s*(' || c_mv || ')(?:(?![a-z0-9])(?!\.\d)|(?=[x×]\d))';
  re_unit_num constant text := '(?<![a-z])(' || c_mv || ')\.?\s*(0\s\d{1,3}(?!\d)|\d+(?:[.,]\d+)?)(?:(?![0-9a-z])|(?=[x×]\d))';
  re_pz_before constant text := '(?<![a-z])(?:pz|pezzi|pcs|p(?=\.\s*\d))\.?\s*(\d+)(?![0-9])(?![.,]\d)(?!\s*(?:' || c_mv || ')(?![a-z])(?!\.?\s*\d))';
  re_pz_after constant text := '(?<![0-9])(\d+)\s*(?:pz|pezzi|pcs)(?![a-z])';
  re_unit_before_number constant text := '(?<![a-z])(?:' || c_mv || ')\.?\s*$';
  re_count_word_after constant text := '^\s*(?:' || c_count_words || ')(?![a-z])';
  re_x_right constant text := '^\s*[x×]\s*(\d+)(?![0-9]*[.,]?[0-9]*\s*(?:cm|mm)\y)';
  re_x_left constant text := '(?<![0-9.,])(\d+)\s*[x×]\s*$';

  d text;
  v_base text; v_factor numeric; v_kind text; v_piece boolean;
  cs_start int[] := '{}'; cs_end int[] := '{}'; cs_n int[] := '{}';
  uf_pos int[] := '{}';
  i int; s int; e int; us int; qe int; qs int; ue int; cnt int;
  q_txt text; u_txt text; gap text; qty numeric; c_base text; c_factor numeric; c_kind text;
  has_cand boolean := false;
  b_start int; b_end int; b_in_base numeric; b_base text;
  v_count int; per_unit numeric; v_norm numeric;
  m text[];
  overlapped boolean; j int;
begin
  o_unit := null; o_price := null;
  if p_price is null or p_price <= 0 then return; end if;

  select * into v_base, v_factor, v_kind from eye_supremo.eye_unit_base_factor(p_unit);
  if v_kind = 'kgl' then
    -- unità frazionaria (g, ml, cl…) con prezzo da pezzo: non è un prezzo credibile al kg/l.
    if v_factor < 1 and p_price / v_factor > 500 then return; end if;
    o_unit := v_base; o_price := round(p_price / v_factor, 4);
    if o_price = 0 then o_unit := null; o_price := null; end if;
    return;
  end if;
  if v_kind = 'other' then return; end if;
  v_piece := (v_kind = 'piece');

  d := replace(coalesce(p_desc, ''), E'\n', ' ');
  if btrim(d) = '' then return; end if;

  -- Marcatori di pezzi (PZ.80, PZ 48, 50PZ): prima «PZ n», poi «n PZ».
  i := 1;
  loop
    s := regexp_instr(d, re_pz_before, 1, i, 0, 'i');
    exit when s = 0;
    e := regexp_instr(d, re_pz_before, 1, i, 1, 'i');
    cnt := eye_supremo.eye_valid_count(regexp_substr(d, re_pz_before, 1, i, 'i', 1));
    i := i + 1;
    if cnt is not null then
      cs_start := cs_start || s; cs_end := cs_end || e; cs_n := cs_n || cnt;
    end if;
  end loop;
  i := 1;
  loop
    s := regexp_instr(d, re_pz_after, 1, i, 0, 'i');
    exit when s = 0;
    e := regexp_instr(d, re_pz_after, 1, i, 1, 'i');
    cnt := eye_supremo.eye_valid_count(regexp_substr(d, re_pz_after, 1, i, 'i', 1));
    i := i + 1;
    -- «GR.25 PZ.100»: il 25 è un contenuto, non un numero di pezzi.
    if substr(d, 1, s - 1) ~* re_unit_before_number then continue; end if;
    if cnt is not null then
      cs_start := cs_start || s; cs_end := cs_end || e; cs_n := cs_n || cnt;
    end if;
  end loop;

  -- Posizioni delle unità lette come «unità poi numero» (codice articolo a sinistra: «603 LT 1»).
  i := 1;
  loop
    us := regexp_instr(d, re_unit_num, 1, i, 0, 'i', 1);
    exit when us = 0;
    uf_pos := uf_pos || us;
    i := i + 1;
  end loop;

  -- Candidati «numero poi unità».
  i := 1;
  loop
    s := regexp_instr(d, re_num_unit, 1, i, 0, 'i');
    exit when s = 0;
    e := regexp_instr(d, re_num_unit, 1, i, 1, 'i');
    us := regexp_instr(d, re_num_unit, 1, i, 0, 'i', 2);
    qe := regexp_instr(d, re_num_unit, 1, i, 1, 'i', 1);
    q_txt := regexp_substr(d, re_num_unit, 1, i, 'i', 1);
    u_txt := regexp_substr(d, re_num_unit, 1, i, 'i', 2);
    i := i + 1;
    if us = any(uf_pos) and us > qe then continue; end if;
    overlapped := false;
    for j in 1 .. coalesce(array_length(cs_start, 1), 0) loop
      if (cs_start[j] <= s and s < cs_end[j]) or (cs_start[j] < e and e <= cs_end[j]) then overlapped := true; end if;
    end loop;
    if overlapped then continue; end if;
    qty := replace(regexp_replace(q_txt, '\s+', '.', 'g'), ',', '.')::numeric;
    select * into c_base, c_factor, c_kind from eye_supremo.eye_unit_base_factor(u_txt);
    if qty > 0 and c_kind = 'kgl' and (not has_cand or s < b_start) then
      has_cand := true; b_start := s; b_end := e; b_in_base := qty * c_factor; b_base := c_base;
    end if;
  end loop;

  -- Candidati «unità poi numero».
  i := 1;
  loop
    s := regexp_instr(d, re_unit_num, 1, i, 0, 'i');
    exit when s = 0;
    e := regexp_instr(d, re_unit_num, 1, i, 1, 'i');
    ue := regexp_instr(d, re_unit_num, 1, i, 1, 'i', 1);
    qs := regexp_instr(d, re_unit_num, 1, i, 0, 'i', 2);
    u_txt := regexp_substr(d, re_unit_num, 1, i, 'i', 1);
    q_txt := regexp_substr(d, re_unit_num, 1, i, 'i', 2);
    i := i + 1;
    overlapped := false;
    for j in 1 .. coalesce(array_length(cs_start, 1), 0) loop
      if (cs_start[j] <= s and s < cs_end[j]) or (cs_start[j] < e and e <= cs_end[j]) then overlapped := true; end if;
    end loop;
    if overlapped then continue; end if;
    -- «285G 16 FETTE»: unità e numero separati da soli spazi e numero seguito da «fette», «pz»… è un conteggio.
    gap := substr(d, ue, qs - ue);
    if gap <> '' and gap ~ '^\s+$' and substr(d, e) ~* re_count_word_after then continue; end if;
    qty := replace(regexp_replace(q_txt, '\s+', '.', 'g'), ',', '.')::numeric;
    select * into c_base, c_factor, c_kind from eye_supremo.eye_unit_base_factor(u_txt);
    if qty > 0 and c_kind = 'kgl' and (not has_cand or s < b_start) then
      has_cand := true; b_start := s; b_end := e; b_in_base := qty * c_factor; b_base := c_base;
    end if;
  end loop;

  -- Numero di pezzi: «X24» a destra, «24X» a sinistra, altrimenti il primo marcatore PZ.
  v_count := null;
  if has_cand then
    m := regexp_match(substr(d, b_end), re_x_right, 'i');
    if m is not null then v_count := eye_supremo.eye_valid_count(m[1]); end if;
    if v_count is null then
      m := regexp_match(substr(d, 1, b_start - 1), re_x_left, 'i');
      if m is not null then v_count := eye_supremo.eye_valid_count(m[1]); end if;
    end if;
  end if;
  if v_count is null and coalesce(array_length(cs_n, 1), 0) > 0 then v_count := cs_n[1]; end if;
  if v_count is not null and v_count <= 1 then v_count := null; end if;

  if has_cand and b_in_base > 0 then
    per_unit := b_in_base;
    if v_count is not null then
      if v_piece and p_qty = v_count then
        null;  -- venduto a pezzi singoli («32GX32» con quantità 32)
      else
        per_unit := b_in_base * v_count;
        if v_piece and p_price / per_unit < 0.25 and p_price / b_in_base >= 0.25 then
          per_unit := b_in_base;
        end if;
      end if;
    end if;
    -- Cartone con il peso di un solo articolo e nessun numero di pezzi: nessuna lettura affidabile.
    if v_kind = 'pack' and v_count is null and b_in_base < 0.1 then return; end if;
    v_norm := p_price / per_unit;
    if v_norm > 500 then return; end if;
    o_unit := b_base; o_price := round(v_norm, 4);
    if o_price = 0 then o_unit := null; o_price := null; end if;
    return;
  end if;

  -- Solo numero di pezzi: ha senso per confezioni/cartoni (o nessuna unità), non per un «pezzo» già singolo.
  if v_count is not null and v_kind <> 'piece' then
    o_unit := 'pz'; o_price := round(p_price / v_count, 4);
    if o_price = 0 then o_unit := null; o_price := null; end if;
  end if;
end;
$$;

revoke all on function eye_supremo.eye_unit_base_factor(text) from public, anon, authenticated;
revoke all on function eye_supremo.eye_valid_count(text) from public, anon, authenticated;
revoke all on function eye_supremo.eye_normalize_price(numeric, numeric, text, text) from public, anon, authenticated;

-- Stato applicato in produzione (9 nov 2026): ricalcolate 82.068 righe su 167.283; poi azzerate le ~120 righe
-- con unità frazionaria e prezzo > 500 €/kg|l (regola sopra); infine `select public.eye_refresh_product_catalog();`.

-- Trigger (applicato come migrazione `central_rows_normalize_trigger`): le righe nuove o modificate con
-- normalized_price NULL e analysis_status = 'product' vengono normalizzate in automatico.
create or replace function eye_supremo.eye_central_rows_normalize_trg()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
declare n record;
begin
  if new.normalized_price is null and new.analysis_status = 'product' then
    select * into n from eye_supremo.eye_normalize_price(new.unit_price, new.quantity, new.original_unit, new.original_description);
    if n.o_price is not null then
      new.normalized_unit := n.o_unit;
      new.normalized_price := n.o_price;
    end if;
  end if;
  return new;
end;
$$;
revoke all on function eye_supremo.eye_central_rows_normalize_trg() from public, anon, authenticated;

drop trigger if exists eye_central_rows_normalize on eye_supremo.eye_central_invoice_rows;
create trigger eye_central_rows_normalize
before insert or update of unit_price, quantity, original_unit, original_description, normalized_price
on eye_supremo.eye_central_invoice_rows
for each row execute function eye_supremo.eye_central_rows_normalize_trg();

-- 9 nov 2026 (sera): «P.36» = 36 pezzi (solo con punto e numero; «PRZ.14» resta escluso). Applicato come migrazione
-- `normalize_price_p_dot_pieces`; 40 righe nuove normalizzate, nessuna già normalizzata è cambiata.

-- 9 nov 2026 (notte): tetto da 500 €/kg|l per le unità frazionarie riapplicato alla funzione attiva
-- (migrazione `normalize_price_fractional_unit_cap`; prima mancava e il trigger rinormalizzava le righe svuotate).
-- Catalogo (migrazione `product_catalog_exclude_extra_rows`): `eye_refresh_product_catalog()` esclude ora
-- carburante, accise, trasporto/spedizione, sconti/omaggi/abbuoni, bollo, cauzioni/imballi, storni/accrediti e le righe
-- con totale <= 0 (note di credito). Definizione precedente salvata in
-- eye_supremo.eye_refresh_product_catalog_def_backup_20261109. Risultato: catalogo 26.409 -> 25.847 voci,
-- 0 voci extra, 0 prezzi negativi. Le righe e le descrizioni non sono state modificate.
