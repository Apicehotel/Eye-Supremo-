# Passaggi di consegna tra agenti

Aggiorna questo file a inizio e fine di ogni compito (una riga per voce, più recente in alto).
Non scrivere segreti o dati personali.

## In corso
_(nessuno)_ — formato: `[agente] ramo — area/file toccati — da quando`_

## Fatto di recente
- [Claude] `fix/normalizzazione-prezzi` (PR #137, release 2.0.47): normalizzatore prezzi unico (€/kg, €/l, €/pz) con confine di parola, notazione col punto, moltiplicatori di confezione e unità CT/CF/SC/N./K./LIT; migrazione locale `2026-11-09-01`; prezzo centrale completato in lettura. Stima sul centrale (167.283 righe): confrontabili ~65% delle righe prodotto, prima ~26%.
- [Claude] release 2.0.46 (PR #135): ricerca prodotti più robusta (parallelo, refusi, fallback locale), costruttore unico del report storico, errori visibili.
- [Claude] 2.0.45 (PR #134): Report storico con scelta della variante anche con dati locali. 2.0.44 (PR #133): «Indietro» torna all'elenco varianti.
- [Claude] 2.0.43 (PR #131): ricerca per materiali, sinonimi e famiglie con gusto/grammatura.

## Aperto / da fare
- Prezzi normalizzati: backfill Supabase fatto il 9 nov 2026 (82.068/167.283 righe, catalogo rigenerato, backup `eye_central_invoice_rows_backup_20261109`). Da fare: ricalcolo per le righe importate in futuro (rilanciare l'UPDATE documentato nella migrazione) e versione online (Vercel) che non normalizza ancora. Rilascio installer (bump versione) in attesa dell'utente.
- Prezzi normalizzati: `75x12` / `33 x24` senza unità (acqua, bibite) non letti; righe non alimentari con capacità nel nome ricevono €/l.
- Bump versione e rilascio dell'installer (la migrazione locale arriva ai PC solo con una release).
- Misurare la ricerca prodotti su un campione di nomi reali del catalogo (~26k).
- Supabase: RLS disattivata su `storage_retention_policy` e `eye_central_product_configs` (decisione dell'utente sulle policy).
- Ruotare la coppia di chiavi S3 degli aggiornamenti dopo la pubblicazione (era passata in chat).
- Tag `v2.0.43` non creato (i tag vanno creati dall'utente o da un ambiente non limitato).
- Login locale senza limite ai tentativi; `npm audit fix` per vite/source-map-js.
