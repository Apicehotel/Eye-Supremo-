# Passaggi di consegna tra agenti

Aggiorna questo file a inizio e fine di ogni compito (una riga per voce, più recente in alto).
Non scrivere segreti o dati personali.

## In corso
_(nessuno)_ — formato: `[agente] ramo — area/file toccati — da quando`

## Fatto di recente
- [Claude] release 2.0.46 (PR #135): ricerca prodotti più robusta (parallelo, refusi, fallback locale), costruttore unico del report storico, errori visibili.
- [Claude] 2.0.45 (PR #134): Report storico con scelta della variante anche con dati locali. 2.0.44 (PR #133): «Indietro» torna all'elenco varianti.
- [Claude] 2.0.43 (PR #131): ricerca per materiali, sinonimi e famiglie con gusto/grammatura.

## Aperto / da fare
- Misurare la ricerca prodotti su un campione di nomi reali del catalogo (~26k).
- Supabase: RLS disattivata su `storage_retention_policy` e `eye_central_product_configs` (decisione dell'utente sulle policy).
- Ruotare la coppia di chiavi S3 degli aggiornamenti dopo la pubblicazione (era passata in chat).
- Tag `v2.0.43` non creato (i tag vanno creati dall'utente o da un ambiente non limitato).
- Login locale senza limite ai tentativi; `npm audit fix` per vite/source-map-js.
