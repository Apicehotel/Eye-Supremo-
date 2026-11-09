-- Catalogo prodotti: prezzi normalizzati (€/kg, €/l, €/pz) con la loro unità.
-- DA APPLICARE SU PRODUZIONE SOLO SU RICHIESTA ESPLICITA DELL'UTENTE.
-- 1) backup delle definizioni; 2) colonna price_unit; 3) eye_refresh_product_catalog preferisce le righe normalizzate
--    (min/avg/max sulle sole righe normalizzate se ce ne sono, altrimenti sul prezzo grezzo, senza unità);
-- 4) eye_central_product_page restituisce price_unit. Dopo: select public.eye_refresh_product_catalog();
create table if not exists eye_supremo.eye_product_page_def_backup_20261109 as
  select now() as backed_up_at,
         pg_get_functiondef('public.eye_central_product_page(text,text,text,integer)'::regprocedure) as definition,
         pg_get_functiondef('public.eye_refresh_product_catalog()'::regprocedure) as catalog_definition;
alter table eye_supremo.eye_product_page_def_backup_20261109 enable row level security;
alter table eye_supremo.eye_central_product_catalog add column if not exists price_unit text;
-- Le due funzioni vanno ridefinite partendo dalla definizione corrente (vedi backup) aggiungendo price_unit.
