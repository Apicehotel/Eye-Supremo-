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

**Versione applicativa:** `2.0.9`

**Novità 2.0.9:** le vecchie variabili d'ambiente PIN/utente centrali vengono ignorate (fine di «Credenziali non valide»), sincronizzazione recensioni corretta, errore credenziali più chiaro.

**Novità 2.0.8:** fattura di riferimento apribile su ogni ricerca prodotto, report storico con tutti i fornitori, ricerca per parte di parola («bombo» trova «bombolino»), riconoscimento prodotti con Open Food Facts (alimentari e non), Ask Fatture completo con integrazione dalla centrale.

**Novità 2.0.7:** stato cache offline a colpo d’occhio (chip + scheda Dashboard, verifica completezza e ripresa automatica), errori Supabase con il motivo del server, PIN predefinito `000000` ripristinato.
**Branch principale:** `main` (modifiche solo via branch + PR)
**Ultimo aggiornamento:** 13 ottobre 2026

### Completato

- archivio locale fatture con import XML FatturaPA, anteprima, duplicati, imponibile, IVA e totale;
- ricerca fatture, prodotti e fornitori con filtri e ordinamento per data, prezzo, fornitore, imponibile e totale;
- catalogo prodotti, classificazione conservativa e storico prezzi per fornitore;
- report storico con confronto prezzi, produttore/marca, unità normalizzate e stampa/PDF;
- recensioni separate per hotel, import MSG/EML/TXT, ranking, temi e alert;
- dashboard, report, destinazione fattura, backup, audit log e sincronizzazione centrale opzionale;
- login locale per profilo utente con PIN; il login sviluppatore non è più obbligatorio;
- tutti i profili condividono gli stessi permessi operativi; gestione utenti e PIN dall'area Sistema;
- Eye AI locale con Qwen/Ollama, agenti interni e fallback deterministico;
- GitHub Actions per test, build Windows e pubblicazione delle GitHub Releases;
- controllo aggiornamenti da **Sistema → Aggiornamenti**, confronto con l'ultima GitHub Release e download diretto dell'installer (fallback locale se serve);
- modalità offline: ricerche, dashboard e dettagli usano SQLite/cache locale quando Supabase o Internet non sono disponibili;
- ricerca dello storico prodotti con suggerimenti, selezione delle varianti e layout responsive a due colonne;
- gestione corretta degli errori Supabase: se il catalogo centrale non è raggiungibile, la schermata resta utilizzabile senza errore 500;
- parsing XML FatturaPA dei riepiloghi fiscali tramite `DatiRiepilogo`, con imponibile, IVA e totale coerenti;
- import PDF/TXT più affidabile e somma delle spese calcolata sulle righe pertinenti;
- autenticazione centrale Supabase verificata per gli utenti `supremo` e `sviluppatore`; i PIN locali e centrali restano sistemi distinti.

### Verificato

- backend: `152 passed`;
- build frontend Vite: riuscita;
- ricerca reale verificata con prodotti `pago` e `limoncello`;
- RPC Supabase del catalogo centrale verificata con risposta dati;
- build Windows locale pronta tramite `scripts\\build_windows.ps1`;
- `EyeSupremo.exe` come app a finestra nativa (WebView2), senza aprire il browser.

### Da completare

- sicurezza accessi: rimuovere il PIN predefinito dalla UI e imporre il cambio PIN al primo accesso;
- pubblicare una GitHub Release coerente con la versione dell'installer dopo rebuild Windows;
- verificare su PC pulito: installazione, doppio clic → finestra app (non browser), primo login, import XML e aggiornamento;
- eventuali aggiornamenti futuri: firma digitale dell'installer e installazione automatica opzionale dopo conferma.

GitHub conserva codice e versioni, non fatture o recensioni reali. L'app controlla le release da GitHub e scarica l'installer solo dopo richiesta dell'utente; l'installazione resta manuale e confermata.

## Hotel preconfigurati

- `gio` — Hotel Giò
- `choco` — Chocohotel
- `brigantino` — Hotel Il Brigantino

## Accesso e permessi

Eye Supremo usa autenticazione locale con PIN e sessione. L'installazione crea i profili **Sviluppatore** e **Supremo** con lo **stesso livello operativo** su tutti gli hotel e sulle funzioni dell'app (fatture, recensioni, configurazione, utenti). I livelli utente (Livello 1 / 2 / 3) sono stati eliminati.

Il PIN predefinito di tutti i profili locali (Sviluppatore, Supremo e nuovi profili) è **`000000`**, ripristinato su richiesta del titolare; può essere cambiato da **Sistema → Utenti e ruoli**. Gli utenti centrali Supabase `supremo` e `sviluppatore` hanno anch’essi PIN `000000` (verificato). I PIN locali e quelli centrali sono sistemi distinti e **non si sincronizzano automaticamente**: se cambi il PIN dell’account centrale su Supabase, aggiorna anche `central_pin` (variabile `EYESUPREMO_CENTRAL_PIN`) su tutti i PC, altrimenti il download cache fallisce con «Credenziali non valide».

Per le recensioni ogni profilo vede **Tutti gli hotel** oltre alle sezioni Giò / Choco / Brigantino.

Per le fatture la visibilità resta aziendale Apice; le fatture **non vengono separate in tre archivi hotel**.

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

**Ricerca fatture:** estesa a **tutte** le righe prodotto dell’archivio locale e della cache — nessun tetto nascosto e **nessun prodotto speciale**. Ogni descrizione riga (limoncello, carta igienica, detergenti, bomboloni, …) è cercabile con varianti/composti; i fornitori sono diversificati in pagina. `limit`/`offset` paginano solo la UI; `total`, totali economici e conteggio fornitori coprono l’intero match set.

**Ask Fatture:** usa solo l’archivio fatture (`area=invoices`). Estrae il prodotto dalla domanda e cerca **tutte** le righe prodotto su locale + cache (+ Supabase se serve); confronta i fornitori su tutto il match set, non solo il vendor più frequente. Allo LLM arrivano ~24 righe diversificate; summary e storico usano tutti i match. Domande tipo fattura più alta / spese semplici restano deterministiche; altrimenti `llama3.2:3b` con escalation a `qwen3:8b`.

**Fattura di riferimento su ogni ricerca prodotto:** ogni riga prodotto (Fatture → risultati locali e cache/centrale, Prodotti → storico acquisti, Ask Fatture → «Dati fatture verificati») ha il pulsante **Apri** che mostra la fattura completa in un pannello laterale, con la riga cercata evidenziata e la fonte (archivio locale, cache del PC, archivio centrale). Backend: `GET /api/eye/invoice-ref/{ref}` dove `ref` è l’id fattura locale o lo `source_hash` centrale; ordine di ricerca: locale → cache PC → Supabase. Se la fattura non è disponibile (né locale né in cache né online) il pannello lo dice chiaramente.

**Report storico completo (tutti i fornitori):** il report storico unisce le fatture importate in locale **e** quelle scaricate nella cache del PC (archivio centrale), senza doppioni (stessa fattura riconosciuta per hash o per fornitore+numero+data). Cercando ad esempio «bomboloni» compaiono tutti i fornitori che li hanno venduti, con prezzi confrontati sulla stessa unità. Ogni acquisto nella matrice ha il link «fattura N» che apre la fattura di riferimento. Se la cache è incompleta il report lo segnala. L’API `GET /api/eye/reports/history-product` include `sources` (righe locali/cache, numero fornitori, `cache_complete`).

**Ricerca per parte di parola:** dal filtro nomi prodotto (elenco Prodotti, suggerimenti e report storico da archivio centrale) una parte di parola di almeno 4 caratteri trova le parole più lunghe: «bombo» trova «bombolino» e «minibombolini», «limon» trova «limoncello». Sotto i 4 caratteri la ricerca resta rigida. Corretto anche un crash del filtro su «carta igienica».

**Cache PC prima di Supabase:** Ask e le liste leggono la cache SQLite locale per **fatture** (`central_invoice_cache`) e **recensioni** (`central_review_cache`). Supabase interviene solo se la cache è vuota; l’aggiornamento resta in background.

**Bootstrap all’installazione:** al primo avvio (o con cache vuota) Eye Supremo scarica in background fatture e recensioni da Supabase nella cache del PC. Poi offline consulta solo quella cache. Manuale: Impostazioni → Sincronizzazione → *Scarica tutto per offline*.

**Stato cache a colpo d’occhio:** nella barra laterale c’è un indicatore (verde = completa, ambra = in corso/non verificata/parziale, rosso = errore o vuota) e nella Dashboard una scheda con barra di avanzamento («X di Y fatture · mancano N»). Il download confronta le fatture locali con il totale centrale: se mancano record (o il fallback ha scaricato solo le prime 500) la cache è marcata *incompleta*, non viene salvato il checkpoint e al prossimo avvio il download riprende da solo. Pulsante *Completa download* per forzarlo. Gli errori di Supabase mostrano il motivo restituito dal server (es. `Supabase 400 su eye_central_invoice_page: Credenziali non valide`) invece del solo «400 Bad Request». API: `GET /cache/bootstrap/status` → `health`, `headline`, `progress`, `invoices{local,remote_total,percent,missing}`, `ready_offline`.

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
- autenticazione locale con PIN e sessione (PIN iniziale da cambiare al primo accesso);
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


## Riconoscimento prodotti (Open Food Facts)

Ogni prodotto in elenco e nella selezione del report storico mostra categoria, marca e provenienza riconosciute dalla descrizione di fattura. Il riconoscimento è **locale e offline**: usa un dizionario di categorie in italiano ricavato dalla tassonomia di [Open Food Facts](https://it.openfoodfacts.org/) (licenza ODbL, © contributori Open Food Facts), integrato con marche e voci non alimentari (energia, lavanderia, imposte…) tipiche delle fatture.

- Dizionario: `backend/app/data/off_categories_it.json`, rigenerabile con `python scripts/build_off_categories.py`.
- Nessuna chiamata all'API di Open Food Facts a runtime (limiti di richieste e uso offline).
- Marche e famiglie si estendono in `backend/app/product_recognition.py` (`BRANDS`, `NON_FOOD`, `EXTRA_FOODS`).
- Prodotti **non alimentari**: oltre alle famiglie manuali (imposte, energia, lavanderia…), le righe senza esito alimentare usano le tassonomie Open Products Facts e Open Beauty Facts (`backend/app/data/off_nonfood_it.json`, rigenerabile con `python scripts/build_nonfood_categories.py`) e mostrano famiglia e sottocategoria (es. «Pulizia e igiene › Shampoo»). Le voci contabili restano manuali.

### Ask Fatture: integrazione dalla centrale
Se la cache PC non è verificata completa, Ask integra sempre i risultati locali con una ricerca su Supabase (timeout 25 s), così un prodotto presente solo nell'archivio centrale mostra tutti i fornitori e non una riga sola.

### Credenziali centrali e variabili d'ambiente
Le vecchie variabili Windows `EYESUPREMO_CENTRAL_USERNAME` e `EYESUPREMO_CENTRAL_PIN` vengono ignorate (causavano «Credenziali non valide» dopo il ripristino del PIN predefinito). Per cambiare le credenziali centrali si usano `EYESUPREMO_CENTRAL_USERNAME_OVERRIDE` e `EYESUPREMO_CENTRAL_PIN_OVERRIDE`.
La sincronizzazione recensioni non invia più un checkpoint vuoto come data (errore «invalid input syntax for type timestamp»), e l'errore «Credenziali non valide» indica utente e lunghezza PIN usati (mai il PIN).

### Ask Fatture: pertinenza dei risultati
Ask tiene solo le righe la cui **descrizione** è il prodotto cercato (non il nome del fornitore) e di famiglia compatibile, usando il riconoscimento prodotti: autofatture/voci contabili e accessori (es. «molla portacarta igienica») non finiscono più nel confronto prezzi. Se l'archivio centrale non risponde, Ask lo segnala con il motivo invece di mostrare un risultato parziale senza avvisi.

### Sinonimi di prodotto
La ricerca tratta «marmellata», «confettura» e la sigla «MARM.» come lo stesso prodotto (le righe di dolci pronti come «crostata alla marmellata» e gli accessori come dispenser o dosatori restano fuori dal confronto prezzi). Nuovi sinonimi si aggiungono in `PRODUCT_FAMILY_ALIASES` (`backend/app/product_taxonomy.py`).

### Un prodotto, più produttori
Cercando un prodotto (es. «crostata», «marmellata») l'elenco e la scelta del report storico mostrano **una sola voce** con tutti i nomi e produttori trovati, così il confronto prezzi per fornitore è unico. Le ricerche dove la misura conta (acqua, carta igienica, A4, lampadine) continuano a proporre le varianti da scegliere. Logica in `collapse_to_product` (`backend/app/product_recognition.py`).

### Simulazione su dati reali (ricerca prodotti)

Verificati banane, birra, caffè, latte, mozzarella, pomodori, prosciutto, uova, yogurt: ogni prodotto resta una sola voce con tutti i produttori. Correzioni: la ricerca per parte di parola scatta in mezzo alla parola solo da 6 caratteri (così «uova» non trova «nuova»), parole di confezione (sgrassato, vassoio, busta) non escludono più un alimento, e «MOZZ.» è riconosciuto come mozzarella.

### Ricerca esatta con le virgolette

Scrivendo la parola tra virgolette (`"olio"`, anche in Ask: «chi mi vende "olio"?») la ricerca trova solo la **parola intera**: niente parti di parola, sinonimi o correzioni (`"olio"` non trova «gasolio»). Senza virgolette resta la ricerca flessibile. In più: «vino» non trova più «bovino/ovino», «olio» non trova «gasolio» (le parole corte contano solo a inizio parola) e i tovaglioli di carta sono «Monouso e tavola» e si uniscono in un solo prodotto, distinti dal servizio di lavanderia.
