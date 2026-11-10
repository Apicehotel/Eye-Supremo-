# Passaggi di consegna tra agenti

Aggiorna questo file a inizio e fine di ogni compito (una riga per voce, più recente in alto).
Non scrivere segreti o dati personali.

## In corso
_(nessuno)_ — formato: `[agente] ramo — area/file toccati — da quando`_

## Fatto di recente
- [Claude] `fix/ordini-lenti` (release 2.0.53): Ordini non restano più in caricamento (query mirate per fornitore, tempo massimo sul centrale, avviso se mancano righe).
- [Claude] `feat/ordini-automatici` (release 2.0.52): Ordini senza caricamenti (fatture locali + cache + righe dal centrale, nome fornitore senza forma societaria) e selettore fornitore con ricerca.
- [Claude] `feat/fattura-evidenzia-righe` (release 2.0.51): nel pannello fattura aperto dallo storico la riga cercata è evidenziata (descrizione reale del punto) e c'è la ricerca tra le righe.
- [Claude] `feat/prezzi-online-e-foglio-condiviso` (release 2.0.50): `price_unit` nel catalogo Supabase e nella tabella Prodotti; foglio ordini condiviso via Supabase (tabella + 2 RPC, sync nel backend). Migrazioni applicate su produzione su richiesta esplicita; backup in `eye_product_page_def_backup_20261109`. Aperto: l'online (Vercel) non ha ancora la pagina Ordini.
- [Claude] `feat/export-ordini-xlsx` (PR #142, release 2.0.49): «Scarica Excel» per il foglio ordini del fornitore. `docs/supabase-catalogo-extra`: catalogo Supabase senza voci extra (26.409 → 25.847), tetto 500 €/kg|l riapplicato alla funzione SQL attiva.
- [Claude] `fix/pezzi-abbreviati` (PR #138, release 2.0.48): «P.36» letto come 36 pezzi (Python + SQL), 40 righe centrali aggiornate. `PRZ.` escluso di proposito (porzioni).
- [Claude] `feat/costi-extra-fornitore` (PR #141): sezione «Costi extra» nella scheda fornitore (carburante, accise, trasporto, sconti, bollo, CONAI, resi, servizi, riferimenti, negativi, righe a 0 €). Aperto: marcare queste righe sul centrale (analysis_status/exclusion_reason) per toglierle dal catalogo; rivedere a mano «servizi/canoni».
- [Claude] `feat/ordini-fornitore` (PR #139, in 2.0.48): tab «Ordini» nella scheda fornitore come il foglio MARR (consegne giornaliere, dettaglio, riepilogo, verifiche, prezzi, fatture, controlli XML), dati dal foglio .xlsx caricato (`supplier_order_sheets`) o, senza foglio, dalle fatture in cache. Aperto: export .xlsx con formule e fogli articolo; leggere ordine/DDT/codice dall'XML; il foglio caricato resta solo sul PC (non su Supabase).
- [Claude] `fix/normalizzazione-prezzi` (PR #137, release 2.0.47): normalizzatore prezzi unico (€/kg, €/l, €/pz) con confine di parola, notazione col punto, moltiplicatori di confezione e unità CT/CF/SC/N./K./LIT; migrazione locale `2026-11-09-01`; prezzo centrale completato in lettura. Stima sul centrale (167.283 righe): confrontabili ~65% delle righe prodotto, prima ~26%.
- [Claude] release 2.0.46 (PR #135): ricerca prodotti più robusta (parallelo, refusi, fallback locale), costruttore unico del report storico, errori visibili.
- [Claude] 2.0.45 (PR #134): Report storico con scelta della variante anche con dati locali. 2.0.44 (PR #133): «Indietro» torna all'elenco varianti.
- [Claude] 2.0.43 (PR #131): ricerca per materiali, sinonimi e famiglie con gusto/grammatura.

## Aperto / da fare
- Prezzi normalizzati: backfill Supabase fatto il 9 nov 2026 (82.068/167.283 righe, catalogo rigenerato, backup `eye_central_invoice_rows_backup_20261109`). Trigger `eye_central_rows_normalize` attivo (righe nuove normalizzate in automatico). Da fare: versione online (Vercel) che non normalizza ancora. Rilascio installer (bump versione) in attesa dell'utente.
- Prezzi normalizzati: `75x12` / `33 x24` senza unità (acqua, bibite) non letti; righe non alimentari con capacità nel nome ricevono €/l.
- Bump versione e rilascio dell'installer (la migrazione locale arriva ai PC solo con una release).
- Misurare la ricerca prodotti su un campione di nomi reali del catalogo (~26k).
- Supabase: RLS disattivata su `storage_retention_policy` e `eye_central_product_configs` (decisione dell'utente sulle policy).
- Ruotare la coppia di chiavi S3 degli aggiornamenti dopo la pubblicazione (era passata in chat).
- Tag `v2.0.43` non creato (i tag vanno creati dall'utente o da un ambiente non limitato).
- Login locale senza limite ai tentativi; `npm audit fix` per vite/source-map-js.
