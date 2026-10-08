# Eye Supremo

Eye Supremo è un applicativo **standalone, local-first e multi-hotel** per analizzare fatture, recensioni, camere, servizi, ranking, storico prezzi e anomalie. Il PC resta pienamente operativo anche senza Internet; Supabase è un ponte opzionale per sincronizzare dati autorizzati tra Hotel Giò, Chocohotel e Hotel Il Brigantino.

## Principi

- **PC = motore principale**: SQLite, import, ricerca, ranking, backup e IA locale.
- **GitHub = codice e versioni**: mai fatture o recensioni reali.
- **Supabase = ponte opzionale**: sync autenticata push/pull, separata dal funzionamento locale.
- **Ollama/Qwen = IA locale**: interpreta dati già recuperati; non rilegge l'intero archivio a ogni domanda.
- **Freeze main**: modifiche generate da agenti solo su branch + PR + revisione umana.

La sezione **Feedback** consente di descrivere un problema, allegare uno screenshot, salvare la segnalazione localmente ed esportarla in JSON per inviarla allo sviluppatore.

## Stato del progetto

**Versione applicativa:** `2.0.2`
**Branch di lavoro:** `integrate/main-align`
**Ultimo aggiornamento:** 8 ottobre 2026

### Completato

- archivio locale fatture con import XML FatturaPA, anteprima, duplicati, imponibile, IVA e totale;
- ricerca fatture, prodotti e fornitori con filtri e ordinamento per data, prezzo, fornitore, imponibile e totale;
- catalogo prodotti, classificazione conservativa e storico prezzi per fornitore;
- report storico con confronto prezzi, produttore/marca, unità normalizzate e stampa/PDF;
- recensioni separate per hotel, import MSG/EML/TXT, ranking, temi e alert;
- dashboard, report, destinazione fattura, backup, audit log e sincronizzazione centrale opzionale;
- login locale per profilo utente con PIN, ruoli e permessi; il login sviluppatore non è più obbligatorio;
- gestione utenti e PIN riservata al ruolo Sviluppatore;
- Eye AI locale con Qwen/Ollama, agenti interni e fallback deterministico;
- GitHub Actions per test, build Windows e pubblicazione delle GitHub Releases;
- controllo aggiornamenti da **Sistema → Aggiornamenti**, confronto con l'ultima GitHub Release e download diretto dell'installer (fallback locale se serve).
- modalità offline: ricerche, dashboard e dettagli usano SQLite/cache locale quando Supabase o Internet non sono disponibili;
- ricerca dello storico prodotti con suggerimenti, selezione delle varianti e layout responsive a due colonne;
- gestione corretta degli errori Supabase: se il catalogo centrale non è raggiungibile, la schermata resta utilizzabile senza errore 500;
- parsing XML FatturaPA dei riepiloghi fiscali tramite `DatiRiepilogo`, con imponibile, IVA e totale coerenti;
- autenticazione centrale Supabase verificata per gli utenti `supremo` e `sviluppatore`; i PIN locali e centrali restano sistemi distinti.

### Verificato

- backend: `70 passed`;
- build frontend Vite: riuscita;
- ricerca reale verificata con prodotti `pago` e `limoncello`;
- RPC Supabase del catalogo centrale verificata con risposta dati;
- build Windows locale pronta tramite `scripts\\build_windows.ps1`;
- `EyeSupremo.exe` come app a finestra nativa (WebView2), senza aprire il browser.

### Da completare

- pubblicare una GitHub Release coerente con la versione dell'installer dopo rebuild Windows;
- verificare su PC pulito: installazione, doppio clic → finestra app (non browser), primo login, import XML e aggiornamento;
- eventuali aggiornamenti futuri: firma digitale dell'installer e installazione automatica opzionale dopo conferma.

GitHub conserva codice e versioni, non fatture o recensioni reali. L'app controlla le release da GitHub e scarica l'installer solo dopo richiesta dell'utente; l'installazione resta manuale e confermata.

## Hotel preconfigurati

- `gio` — Hotel Giò
- `choco` — Chocohotel
- `brigantino` — Hotel Il Brigantino

## Accesso e ruoli

Eye Supremo usa autenticazione locale con PIN e sessione. L'installazione crea già i profili **Sviluppatore** e **Supremo**, entrambi con un PIN iniziale temporaneo (non riportato qui): lo Sviluppatore deve sostituirlo al primo accesso dall'area Utenti e ruoli. Gli altri profili vengono creati localmente dallo Sviluppatore con il permesso desiderato.

- **Sviluppatore**: accesso completo, configurazione, utenti e manutenzione.
- **Supremo**: visibilità globale operativa sui tre hotel.
- **Livello 1 / 2 / 3**: accesso operativo limitabile all'hotel assegnato e alle esclusioni configurate.

Per le recensioni, Sviluppatore e Supremo vedono **Tutti gli hotel** oltre alle tre sezioni Giò/Choco/Brigantino. Gli utenti assegnati a una sola struttura vedono solo quella.

Per le fatture la visibilità resta aziendale Apice con esclusioni per categoria/prodotto/fornitore/parola chiave; le fatture **non vengono separate in tre archivi hotel**.

## Fatture: archivio unico Apice

Import principale: **XML FatturaPA, TXT e PDF**.

Pipeline:

1. hash SHA-256 e controllo duplicati;
2. parsing e anteprima;
3. conferma esplicita;
   nella schermata lotto è possibile confermare una singola fattura oppure tutte le fatture pronte;
4. classificazione righe;
5. voci contabili non utili all'analisi restano nella fattura ma vengono escluse dalla ricerca prodotto;
6. indicizzazione FTS5;
7. confronto prezzi e creazione alert quando applicabile.

La sezione **Destinazione fattura** è separata dall'import: una fattura resta dell'archivio centrale Apice e può essere marcata facoltativamente come `Generale / Apice`, `Hotel Giò`, `Chocohotel` o `Hotel Il Brigantino` per filtri e analisi.

Le domande di spesa sommano **le righe pertinenti**, non il totale completo delle fatture che le contengono.

## Report storico prodotto

Il modulo **Report storico** riprende la logica dell'Excel operativo e la rende automatica.

Ricerca:

`Prodotto → Produttore/Marca → Fornitore → date → prezzi`

In alto mostra subito:

- prezzo iniziale + data;
- prezzo medio;
- miglior prezzo + data;
- ultimo prezzo + data;
- fornitore mediamente più conveniente.

Per ogni fornitore vengono calcolati prezzo iniziale, medio, migliore e ultimo. Ogni nuovo prezzo è confrontato con il precedente con indicazione `↑`, `↓` o `=` e variazione in euro/%.

I confronti non mescolano unità incompatibili: Eye Supremo confronta i fornitori usando la stessa unità normalizzata (`€/kg`, `€/L`, `€/pz`, ecc.).

### Stampa

Il report ha un layout dedicato **A4 orizzontale**. Quando le date diventano troppe vengono suddivise in più pagine; su **ogni pagina** vengono ripetuti prodotto, produttore/marca e fornitore, così ogni prezzo mantiene sempre il proprio riferimento. La UI espone `Stampa / PDF` e genera pagine compatte pensate per la stampa, non una semplice schermata web ridotta.

## Ricerca veloce

La ricerca parte mentre si digita:

1. **SQLite FTS5** con prefix index;
2. SQL filtrato;
3. **RapidFuzz** come fallback;
4. Qwen solo per interpretazione finale.

L'evoluzione prevista per l'archivio massivo usa prodotto canonico, alias/anti-alias, classificazione `Food & Beverage` / `Non Food`, vector search locale e Qwen solo sui casi ambigui. Similarità testuale non equivale a equivalenza semantica: per esempio `bombolone` e `bombola` devono restare separati.

## Recensioni

Le recensioni sono divise per hotel. Prima si seleziona **Giò / Choco / Brigantino**, poi si caricano i file: tutte le recensioni estratte ereditano l'hotel scelto.

Formati supportati:

- **Outlook `.msg`**;
- EML;
- TXT.

Un singolo `.msg` può contenere **più recensioni**: il parser separa i blocchi, prova a riconoscere Booking/Google/TripAdvisor, camera, data, voto e testo, e crea più record dallo stesso messaggio. Messaggi che non sembrano recensioni vengono segnalati invece di essere importati alla cieca.

## Eye AI e agenti interni

Eye AI usa **Qwen 3 8B** tramite Ollama con un orchestratore locale. La UI principale chiama `/api/eye/agents/ask`; l'orchestratore decide quali specialisti servono e restituisce anche il piano eseguito.

Agenti interni:

- `router` — comprende l'intento;
- `products` — ricerca prodotto, alias e storico;
- `classifier` — classifica Food & Beverage / Non Food e sottocategorie;
- `invoices` — dati fattura e fornitore;
- `prices` — storico, medie, minimi e variazioni;
- `reviews` — recensioni, camere, servizi e ranking;
- `verifier` — controlla unità incompatibili e falsi positivi;
- `answer` — genera la risposta finale breve e verificabile.

Gli specialisti che leggono il database possono lavorare in parallelo, ma **ognuno apre una propria sessione SQLAlchemy/SQLite**: non condividono la stessa sessione tra thread. Somme, medie, ranking e confronti restano deterministici; Qwen viene usato soprattutto per interpretazione e sintesi.

La chiamata Ollama usa **structured output JSON Schema** (`answer`, `facts`, `confidence`). Se Ollama non è disponibile, l'orchestratore ricade sul motore deterministico locale. L'endpoint `/api/eye/agents/registry` espone il registro degli agenti e dei tool consentiti.

Durante l'installazione Windows lo script incluso installa Ollama se necessario e scarica automaticamente i modelli. Sono necessari Internet e spazio disco locale; i modelli non vengono committati nel repository né incorporati nell'EXE per le loro dimensioni.

### Layer mirror IA (PC ufficio)

Eye Supremo non forza un unico modello pesante. Usa un **layer mirror** sobrio:

1. **Deterministico** — SQLite calcola e recupera i dati;
2. **Veloce** (`llama3.2:3b`) — sintesi di default, adatta ai PC ufficio;
3. **Qualità** (`qwen3:8b`) — escalation solo se il veloce fallisce o ha confidenza bassa.

Policy di default: `fast_first`. In Impostazioni → IA locale si può scegliere anche `fast_only` o `quality`.

**Ask performante:** contesto ridotto (max ~12 righe), report storico solo se serve, risposte fattuali (es. fattura più alta / spese semplici) senza Ollama, generazione corta su modello veloce con `keep_alive` e cache dei modelli installati.

**Cache PC prima di Supabase:** Ask e le liste leggono la cache SQLite locale per **fatture** (`central_invoice_cache`) e **recensioni** (`central_review_cache`). Supabase interviene solo se la cache è vuota; l’aggiornamento resta in background.

**Bootstrap all’installazione:** al primo avvio (o con cache vuota) Eye Supremo scarica in background fatture e recensioni da Supabase nella cache del PC. Poi offline consulta solo quella cache. Manuale: Impostazioni → Sincronizzazione → *Scarica tutto per offline*.

Modelli inclusi nel completamento automatico:

```text
llama3.2:3b          # layer veloce (mirror)
qwen3:8b             # layer qualità
qwen3-embedding:0.6b
```

Il file `scarica-modelli-ia.bat` resta disponibile nella cartella dell'app per ripetere o completare il download dei modelli.

## Alert

Il dominio supporta alert persistenti per prezzo/anomalie. La pipeline fatture può generare alert quando il prezzo corrente supera in modo rilevante lo storico. Le righe contabili escluse non generano alert prodotto.

## Spazio dati separato

Eye Supremo condivide temporaneamente l'infrastruttura Supabase di MultiHotel per evitare un secondo progetto/costo, ma ha un confine applicativo dedicato: schema logico `eye_supremo` + bucket privato `eye-invoices`. Le tabelle legacy `public.eye_central_*` restano disponibili durante il cutover per non rompere installazioni esistenti. HotelGio è fuori scope e non viene modificato. Vedi [docs/SUPABASE_SPACE.md](docs/SUPABASE_SPACE.md).

## Ponte Supabase

Sul progetto **Apice MultiHotel** sono presenti:

- `eye_sync_memberships`
- `eye_sync_objects`
- Edge Function `eye-supremo-sync`
- tabelle centrali `eye_central_invoices`, `eye_central_invoice_rows`, `eye_central_suppliers`;
- funzione SQL `eye_central_invoice_page` per lettura autenticata paginata;
- cache SQLite locale `central_invoice_cache`, usata per elenco fatture veloce;
- la prima apertura su un PC vuoto avvia automaticamente la replica in background;
- la ricerca di prodotto/famiglia usa ancora l'indice centrale quando la cache non contiene le righe.
- recensioni: `eye_central_reviews`, upsert autenticato all'importazione e pull nella cache `central_review_cache`;
- endpoint diagnostici: `/api/eye/central/sync/status` e `/api/eye/reviews/sync/status`.

L'Edge Function richiede JWT valido. `developer` e `supremo` possono essere configurati per lettura globale; gli altri utenti ricevono solo gli hotel autorizzati dalla membership server-side.

Variabili locali in `.env.example`:

```text
EYESUPREMO_SYNC_ENABLED=false
EYESUPREMO_SUPABASE_URL=
EYESUPREMO_SUPABASE_PUBLISHABLE_KEY=
EYESUPREMO_SUPABASE_ACCESS_TOKEN=
```

La replica centrale è disponibile con le credenziali Eye dell'utente centrale (non riportate qui; vanno impostate in locale tramite variabili d'ambiente). L'app continua a funzionare offline sui dati già replicati; il percorso legacy JWT resta opzionale per gli oggetti multi-hotel.

## Avvio sviluppo

Requisiti: Python 3.11+ e Node 20+.

```powershell
setup.bat
start.bat
```

API: `http://127.0.0.1:8000/api/docs`
UI dev: `http://127.0.0.1:5173`

## Installer Windows (app nativa)

Il PC finale **non deve avere Python o Node**. L'eseguibile è un'**app Windows a finestra** (WebView2), non una pagina aperta nel browser.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Lo script compila React, crea `dist/EyeSupremo.exe` con PyInstaller (`--windowed` + pywebview) e incorpora la UI. `installer/EyeSupremo.iss` con Inno Setup 6 produce `release/EyeSupremo-Setup.exe`.

- Doppio clic su Eye Supremo → si apre **solo la finestra dell'app** (icona taskbar, senza barra indirizzi).
- Nessuna console CMD e nessun Chrome/Edge con URL `http://127.0.0.1:8765`.
- Serve il runtime **Microsoft Edge WebView2** (già presente su Windows 10/11 aggiornati).
- I dati restano in `%LOCALAPPDATA%\EyeSupremo`, separati dall'eseguibile.

`start.bat` resta solo per lo sviluppo (Vite + browser).

## Test e CI

```powershell
cd backend
pytest -q
cd ..\frontend
npm ci
npm run build
```

La PR esegue automaticamente backend test + frontend build e la pipeline Windows genera l'installer.

## Sicurezza

- dati reali locali per default;
- autenticazione locale con PIN e sessione;
- ruolo ricavato dalla sessione, non accettato liberamente dal browser dopo la configurazione;
- hotel delle recensioni limitato ai permessi utente;
- agenti con strumenti dichiarati e limitati;
- sessioni database isolate per worker concorrente;
- Qwen non modifica direttamente fatture o prodotti;
- upload con limiti e nomi generati;
- hash duplicati;
- audit log;
- sync remota centrale autenticata con PIN e paginazione;
- nessun token reale committato.

## Limitazioni note

- il parser `.msg` usa euristiche sui digest reali e va affinato progressivamente sui formati di posta che incontriamo;
- il primo popolamento della cache può richiedere alcuni minuti; le aperture successive leggono SQLite;
- `qwen3-embedding:0.6b` è predisposto, mentre FTS5 + RapidFuzz sono ancora il motore di retrieval attivo; la ricerca vettoriale/canonicalizzazione massiva sarà il passo successivo quando verrà caricato l'archivio delle fatture.
