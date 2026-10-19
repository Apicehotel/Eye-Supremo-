# Attivazione della 2.0.15

La versione contiene le modifiche utenti centrali integrate con la PR 85 e le
correzioni di dashboard, backup e richieste concorrenti. Frontend, API, updater e
nome dell'installer riportano la stessa versione, verificata da un test automatico.

## Stato dell'attivazione

È stato creato un punto di ripristino delle parti interessate in
`eye_supremo_backup_2015_20261019`: profili e definizioni delle RPC precedenti.
Lo schema è privato, con RLS e senza accesso `anon`/`authenticated`.
Non contiene una copia delle fatture o delle recensioni, che la migrazione non
modifica. Non sostituisce i backup completi del progetto Supabase.

Migrazione e distribuzione delle funzioni non sono state eseguite: la revisione
automatica richiede un'approvazione esplicita del cambiamento di autenticazione in
produzione. Non pubblicare l'installer prima dell'attivazione e della verifica.

## Sequenza di rilascio

1. Approvare ed eseguire l'attivazione descritta in `CENTRAL_IDENTITY.md`, limitata
   al progetto Apice MultiHotel e agli oggetti Eye Supremo.
2. Verificare login e gestione utenti su due installazioni con database separati:
   primo accesso online, secondo login offline, cambio PIN, disattivazione e nuova
   verifica quando ritorna la connessione. La CI verifica già i contratti del
   servizio su PostgreSQL 17 e due archivi SQLite indipendenti; la prova su PC
   Windows reali resta parte del rollout.
3. Integrare la PR della 2.0.15 dopo CI e build Windows riuscite. Il messaggio di
   integrazione deve contenere `[release]` per avviare la pubblicazione su `main`;
   in alternativa usare l'avvio manuale del workflow o un tag `v2.0.15`.
4. Il workflow ricava e valida la versione, costruisce l'eseguibile, esegue lo smoke
   test e pubblica `EyeSupremo-Setup-2.0.15.exe` sul commit effettivamente compilato.
5. Aggiornare i PC. Ritirare le credenziali condivise precedenti soltanto quando
   tutte le installazioni coinvolte sono state aggiornate e verificate. Non
   disattivarle durante il rollout: le vecchie versioni ne hanno ancora bisogno.

## Ripristino

Se l'attivazione non supera le verifiche, non distribuire il nuovo installer.
Le definizioni RPC precedenti sono salvate nel punto di ripristino e il gateway
precedente è recuperabile dalla revisione GitHub antecedente alla PR 85.
Ripristinare le funzioni e il gateway in modo coordinato, senza eliminare dati
operativi né reimpostare i PIN degli utenti. Le nuove tabelle sono additive e
possono rimanere senza essere utilizzate durante l'analisi del problema.
