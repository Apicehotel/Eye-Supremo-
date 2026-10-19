# Utenti centrali Eye Supremo

## Comportamento

Supabase è la fonte autorevole dei profili. Il PC resta il motore di fatture,
recensioni e ricerche offline. Il registro utenti esistente nello schema
`eye_supremo` viene conservato, inclusi i verificatori PIN: nessun utente reale
viene creato, cancellato o reimpostato dalla migrazione.

- Il login usa username e PIN personali. Il primo accesso su ogni PC richiede Internet.
- Dopo un login online riuscito, SQLite conserva un verificatore PBKDF2 con sale
  casuale soltanto per quell'utente e una scadenza offline di 7 giorni (configurabile
  da 1 a 30). Non scarica i verificatori degli altri utenti.
- Un login offline non rinnova la scadenza. Una sessione locale non può superarla.
- La sessione centrale dura 12 ore. Il token è mantenuto solo nella memoria del
  backend; non è salvato in SQLite, nel browser o nei log. Sul server è registrato
  soltanto il digest SHA-256 del token.
- Il riavvio del backend richiede un nuovo login con PIN. Se il PC è offline e
  la lease è valida, il login usa il verificatore già memorizzato. Le sessioni
  precedenti non vengono ripristinate senza questa verifica.
- Il riavvio non reimposta i PIN. Nella modalità locale precedente le sessioni
  ancora valide restano utilizzabili come prima.
- Creazione utenti, elenco centrale, cambio PIN e attivazione richiedono una sessione
  centrale valida. Una scrittura remota fallita non crea un profilo locale divergente.
- I nuovi utenti hanno ruolo `supremo`; i ruoli operativi ammessi restano `developer`
  e `supremo`, con gli stessi permessi come nelle versioni precedenti.

Cambio PIN e disattivazione incrementano la versione dell'identità e revocano tutte
le sessioni centrali dell'utente. Sui PC con sessione centrale attiva il controllo
avviene al massimo ogni 60 secondi di utilizzo; le richieste dati remote verificano
il token a ogni chiamata. Le sessioni offline verificano ogni 60 secondi di utilizzo se il servizio è
tornato disponibile: in tal caso richiedono un nuovo login online prima di
continuare. Senza connessione possono continuare entro la lease già concessa. Una revoca non può essere conosciuta
da un computer scollegato. Un nuovo rifiuto esplicito del server non abilita mai
il fallback offline. La successiva verifica richiede le credenziali aggiornate.

## Attivazione dopo la revisione della PR

La PR include codice e migrazione; non distribuisce modifiche in produzione.

1. Eseguire un backup del progetto **Apice MultiHotel** e verificare che lo schema
   `eye_supremo` contenga già gli oggetti descritti in `SUPABASE_SPACE.md`.
2. Applicare `supabase/migrations/20261019212228_central_identity_sessions.sql`.
   È aggiuntiva e ripetibile; aggiorna i controlli di autenticazione delle RPC Eye
   senza cambiare firme o risultati. Non applicare di nuovo le vecchie SQL numerate
   al progetto condiviso e non intervenire sul progetto separato HotelGio.
3. Distribuire `eye-identity` e la versione aggiornata di `eye-central-gateway`
   dal contenuto di `supabase/functions`. Entrambe usano il segreto server
   `SUPABASE_DB_URL` già usato dal gateway. `supabase/config.toml` specifica
   `verify_jwt=false`: le funzioni verificano autonomamente PIN e token opachi.
   Non esporre la stringa di connessione ai PC o al frontend.
4. Verificare login, creazione di un utente di prova, login su un secondo PC,
   cambio PIN e disattivazione. Poi aggiornare gli installer dei PC.
5. Gli utenti già presenti solo in SQLite devono essere creati esplicitamente nel
   centrale da un operatore autorizzato: non vengono promossi automaticamente.
   Il primo login con il profilo centrale collega il nome al profilo locale.

`EYESUPREMO_CENTRAL_IDENTITY_ENABLED=true` è il comportamento predefinito. Se il
servizio centrale non è ancora installato, il login informa che deve essere
aggiornato: non passa silenziosamente all'autenticazione locale. La modalità locale
preesistente resta disponibile soltanto tramite configurazione esplicita a `false`.

Le vecchie installazioni continuano temporaneamente a usare le RPC con PIN e il
gateway precedente. Dopo aver aggiornato tutti i PC occorre ritirare le credenziali
condivise legacy e il relativo percorso di accesso. Questa PR conserva tale
compatibilità per evitare un'interruzione sulle installazioni non aggiornate.

## Sicurezza e test

Le tabelle utenti/sessioni/limiti hanno RLS abilitata e nessun accesso diretto
`anon`/`authenticated`. Il helper di autenticazione è privato e `SECURITY INVOKER`;
le RPC dati esistenti mantengono controlli espliciti di identità/ruolo. Il servizio
utenti applica limiti per IP e username e non restituisce hash PIN. Nessuna funzione
nuova pubblica con `SECURITY DEFINER` viene aggiunta.

La CI esegue test Python per cache, primo accesso, isolamento delle identità,
operazioni utente e due database SQLite indipendenti. I test Python bloccano
connessioni HTTP non simulate. Il job `central-identity` verifica le funzioni e
prova login, creazione, revoca, rate limit e privilegi su PostgreSQL locale.
Il test di integrazione rifiuta URL esterni e richiede il database
`eye_identity_test`; non deve essere eseguito su dati reali.
