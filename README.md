# Eye Supremo

Eye Supremo è un applicativo **standalone, local-first e multi-hotel** per analizzare fatture, recensioni, camere, servizi, ranking, storico prezzi e anomalie. Il PC resta pienamente operativo anche senza Internet; Supabase è un ponte opzionale per sincronizzare dati autorizzati tra Hotel Giò, Chocohotel e Hotel Il Brigantino.

## Principi

- **PC = motore principale**: SQLite, import, ricerca, ranking, backup e IA locale.
- **GitHub = codice e versioni**: mai fatture o recensioni reali.
- **Supabase = ponte opzionale**: sync autenticata push/pull, separata dal funzionamento locale.
- **Ollama/Qwen = IA locale**: interpreta dati già recuperati; non rilegge l'intero archivio a ogni domanda.
- **Freeze main**: modifiche generate da agenti solo su branch + PR + revisione umana.
- **Hosting online (opzionale)**: un solo container Docker (`Dockerfile`) con API + frontend e dati nel volume `/data`; vedi [docs/DEPLOY_ONLINE.md](docs/DEPLOY_ONLINE.md). Non sostituisce l'uso locale sul PC.

La sezione **Feedback** consente di descrivere un problema, allegare uno screenshot, salvare la segnalazione localmente ed esportarla in JSON per inviarla allo sviluppatore.

## Stato del progetto

**Versione applicativa:** `2.0.45`

**Novità 2.0.28 → 2.0.45** (le versioni 2.0.28–2.0.36 sono state allineate in un'unica release; poi 2.0.37, 2.0.38, 2.0.39, 2.0.42, 2.0.43, 2.0.44 e 2.0.45):

- **2.0.43 – Ricerca per materiali, sinonimi e famiglie:** `carta`/`plastica`… trovano i prodotti fatti di quel materiale (non il cibo avvolto), «bombolone choco» = «choco bombolone», `marmellata` copre marm/confet/confettura, varianti ordinate per gusto e grammatura (vedi sezione dedicata). Include il fix del Report storico che non trovava i prodotti.
- **2.0.44 – Report storico, tasto Indietro:** dopo aver scelto una variante dall'elenco prodotti, «Indietro» torna all'elenco (anche a più livelli) invece di svuotare la ricerca; senza elenco precedente azzera la ricerca come prima.
- **2.0.45 – Report storico, scelta della variante:** anche con fatture importate in locale, una ricerca che riguarda gusti o formati diversi (es. «marmellata», «marmellata fragola») mostra prima l'elenco delle varianti (gusto + grammatura) invece di mescolarle in un solo storico; il filtro «carta» lato schermata è stato tolto perché ora decide il backend (un bicchiere di carta è un prodotto di carta).

- **Ricerca prodotti deterministica:** nuovo modulo `backend/app/deterministic_product_search.py` con test di regressione. Nel **Report storico** i risultati non pertinenti (es. cercando «carta») sono filtrati da `isUsefulHistoryMatch` in `frontend/src/pages/HistoricalReport.tsx` (2.0.42).
- **Report storico:** mostra ogni osservazione anche se più fatture hanno la stessa data; nuovi filtri **fornitore** e **periodo** con KPI e confronti fornitori ricalcolati; **export CSV** (`eye-storico-prodotti.csv`, separatore `;`, UTF-8 con BOM).
- **Archivio file fatture:** nuova pagina con ricerca locale (numero, fornitore, ecc.) e download dell'XML originale (`/api/eye/invoice-files`); se il file non è sul PC compare «XML non disponibile su questo PC».
- **Recensioni per utente:** permesso `can_view_reviews` (predefinito: sì), gestibile da **Utenti**; chi non lo ha non vede le recensioni né le relative API. Migrazione locale `2026-10-29-01` e migrazione Supabase `20261029095503_add_review_visibility_permission.sql`. Aggiunti anche i filtri camere Jazz & Wine.
- **Aggiornamenti via Supabase:** l'app controlla e scarica l'installer dall'Edge Function `eye-updates` (bucket privato `eye-updates`, serve la sessione centrale, verifica SHA-256). Il tag `v*` fa partire `release-windows.yml`, che compila, fa lo smoke test e pubblica con `scripts/publish_eye_update.py` (ultime 5 versioni conservate). Non si usano più le GitHub Releases.
- **Importatore archivi:** `scripts/import_archives_supabase.py` carica fatture (XML/P7M) e recensioni (MSG) nei bucket privati Supabase; riprendibile, protetto da path traversal, con deduplica per contenuto. Richiede variabili d'ambiente lato server (mai nel repo).
- **Versione online:** Dockerfile unico (API + frontend, vedi [docs/DEPLOY_ONLINE.md](docs/DEPLOY_ONLINE.md)) e frontend Vercel in sola lettura con layout smartphone: dettagli nella sezione «Versione online».
- **CI:** scansione di sicurezza SkillSpector su PR e push (`.github/workflows/skillspector.yml`).

**Novità 2.0.27:** pagina «Salute dati» con conteggi locali, sincronizzati, errori import, recensioni incomplete, ultimi sync e backup; installer Windows più chiaro e con IA locale opzionale.

**Novità 2.0.26:** pulsante «Invia a Supabase» in Recensioni: rimanda al centrale le recensioni salvate solo sul PC (mai sincronizzate), senza doppioni (endpoint `POST /api/eye/reviews/sync/push`). Prima la sync partiva solo al momento del caricamento file.

**Novità 2.0.25:** Media camere interattiva: clic su una riga apre le recensioni di quella camera (voto, data, autore, voti per tag, testo); clic su una media Booking/Google/TripAdvisor mostra solo quella fonte.

**Novità 2.0.24:** pagina Ranking più focalizzata: prima le quattro classifiche (top 5), poi lo storico delle sole camere sotto soglia e le segnalazioni anonime, entrambi richiudibili. Verificati i duplicati: nessun doppione creato dai caricamenti recenti.

**Novità 2.0.23:** l'app installata è una cartella (`EyeSupremo.exe` + file di supporto) invece di un unico `.exe` che si estraeva in Temp: risolve l'errore «Failed to load Python DLL … python312.dll» all'avvio dopo l'installazione. L'installer sostituisce il vecchio `.exe` senza perdere i dati (sono in `%LOCALAPPDATA%\EyeSupremo`).

**Novità 2.0.22:** il pulsante **Carica file** delle Recensioni non è più muto con "Tutti gli hotel" selezionato: spiega di scegliere prima un singolo hotel nelle schede in alto, poi apre la selezione file.

**Novità 2.0.21:** un numero camera è fatto di cifre (es. 325, 4407, 1108A): parole lette per errore dalle vecchie importazioni ("pulita", "super", "ampia", "Superior"…) non compaiono più come camere in Media camere, nello storico e nei ranking; quelle recensioni risultano senza camera. Controllo in `_valid_room` (`backend/app/routers/eye.py`) e in `frontend/src/lib/roomAverages.ts`.

**Novità 2.0.20:** in Media camere i filtri **Zona** (Cantine Wine) e **Pavimento** (moquette) sono nella stessa riga degli altri filtri (ricerca, voto per tag, ordinamento, voti minimi) invece che in alto a destra.

**Novità 2.0.19:** nelle email con più ospiti, un ospite senza numero camera non eredita più la camera salvata sull'intera email (che poteva essere un numero letto male, es. "10" al posto di "325"): resta senza camera invece di sporcare le medie di una camera inesistente.

**Novità 2.0.18:**

- **Voti per tag:** i voti per categoria scritti nei digest (Staff, Pulizia, Comfort, Posizione, Servizi, Qualità/prezzo, Letti, Colazione, Wi-Fi, Vista dalla camera, Camere, Ristorante) sono letti per ogni recensione e mostrati come etichette nelle recensioni e nello storico. In **Media camere** un menu "Voto per tag" cambia le medie da generale al tag scelto, sempre separate per fonte e sulla scala della fonte. Lettura in `extract_category_scores` (`backend/app/review_importers.py`); i voti per tag sono calcolati alla lettura dal testo, quindi valgono anche per le recensioni già archiviate.
- **Date non più lette come voti:** `in 15/10 out 16/10` o `26/10/24` non diventano più "15/10" o "26/10" come voto generale: si legge il voto sulla riga dell'ospite.

**Novità 2.0.17:**

- **Recensioni solo voto:** senza testo scritto dall'ospite contano nelle medie ma non compaiono come righe; un riquadro le riassume per fonte e voto.
- **Recensioni → Media camere:** pagina a sé con la media dei voti per camera, separata per fonte (Booking su 10, Google e TripAdvisor su 5); i voti fuori scala sono ignorati e segnalati.
- **Filtro camere "Cantine Wine":** menu a tendina nelle Recensioni (e in Media camere) per filtrare l'Hotel Giò per zona: 1 Cantine Wine (126–131), 2 Cantine Wine (225–233), 3 Cantine Wine (326–332), 4 Cantine Wine (426–434), oppure tutte le Cantine Wine insieme. Le camere fuori elenco restano visibili solo con "Tutte le camere". Un secondo menu **Pavimento** (indipendente dalla zona) filtra le camere con moquette dell'Hotel Giò: 125, 211, 218, 221, 224, 312, 323, 412 (oppure "Senza moquette"); i due filtri si combinano.
- **Fonte corretta nelle email miste:** la fonte (Booking/Google/TripAdvisor) si decide dai segnali della singola recensione (numero prenotazione, link profilo Google/TripAdvisor, "su Google"), non più dal piè di pagina che cita tutte le piattaforme; le recensioni Google/TripAdvisor in coda a una email Booking vengono separate e il loro voto "N/5" è letto, così Media camere non le conta più come Booking. Codice in `backend/app/review_importers.py`.
- **Parole negative negate:** la negazione ribalta il giudizio anche se rinforzata ("non è per nulla lontano", "buffet non per nulla vuoto", "per niente", "affatto", "nemmeno", "privo di"): più marcatori insieme contano come una sola negazione. Aggiunte come parole negative "vuoto/vuota/vuoti/vuote" e "lontani/lontane". Elenchi e finestra di negazione in `backend/app/eye_services.py` (`NEGATIONS`, `NEGATION_WINDOW`).
- **Importazione recensioni affidabile:** voti con la virgola accettati, un blocco difettoso non ferma il file, recensioni già caricate saltate (con conteggio), voto salvato sempre visibile.
- **Caricamento multiplo senza doppioni:** si possono selezionare molti file insieme (inviati a gruppi di 25, con avanzamento). Lo stesso file scelto due volte viene ignorato; una recensione già presente (testo identico, oppure già contenuta in una vecchia email salvata intera) non viene ricaricata. Alla fine il messaggio indica quante recensioni sono state importate, quante erano già presenti, quanti file ripetuti sono stati ignorati e i primi problemi da verificare. Oltre 200 file per volta il resto non viene elaborato e viene segnalato.

**Novità 2.0.16:** nella sezione Recensioni → Ranking ogni camera mostra l’andamento del voto nel tempo: i periodi positivi restano nello storico, mentre una nuova segnalazione negativa apre un nuovo intervallo con le cause rilevate. Le recensioni con difetti possono inoltre essere sincronizzate nel foglio camere senza sovrascritture o doppioni.

**Novità 2.0.15:** profili centrali condivisi con login personale e accesso offline autorizzato; PIN conservati al riavvio; dashboard unificata senza doppioni e valida anche con sole note di credito; backup SQLite coerente e verificato; ricerche con annullamento delle richieste superate; dipendenze frontend fissate alle versioni del lockfile. La pubblicazione richiede prima l'attivazione descritta in `docs/CENTRAL_IDENTITY.md`.

**Novità 2.0.14:** nella scheda prodotto del catalogo c'è «Pezzi per confezione» (es. 6 per un cartone): il report storico mostra prezzo e quantità al pezzo. Il numero vale per il prodotto ed è salvato in `product_configs` (campo `pieces_per_pack`). **Installer:** il file si chiama `EyeSupremo-Setup-<versione>.exe` (la versione è nel nome, non si sovrascrive nei download); per ogni release aggiornare anche `OutputBaseFilename` in `installer/EyeSupremo.iss`.

**Novità 2.0.13:** il report storico mostra di nuovo il pulsante «fattura N» (apre la fattura con tutte le righe acquistate); ricerca provata su nomi reali delle fatture: «mozzarella» non lascia più passare tutto e il confronto a somiglianza non confonde più crostata/costa, succhi/sacchi, sfoglia/foglia. **Unisci prodotti:** nel catalogo spunta due o più voci e premi «Unisci»: la scelta viene salvata (tabella `settings`, chiave `product_groups`) e vale per catalogo e report storico; «separa» annulla. API: `GET/POST/DELETE /api/eye/product-groups`.

**Novità 2.0.12:** le voci dello stesso prodotto (es. crostata alla marmellata / crostata marmellata / crostate marmellate) si fondono in una sola anche mentre si scrive o con ricerche lunghe.

**Novità 2.0.11:** ricerca a più parole («crostata marmellata»): servono tutte le parole, con plurali e sinonimi, e i prodotti restano insieme in un'unica voce.

**Novità 2.0.10:** ricerca prodotti più precisa (un prodotto = una voce con tutti i produttori), virgolette per la parola esatta (`"olio"`), niente più falsi match (uova/nuova, vino/bovino, olio/gasolio), tovaglioli di carta uniti.

**Novità 2.0.9:** le vecchie variabili d'ambiente PIN/utente centrali vengono ignorate (fine di «Credenziali non valide»), sincronizzazione recensioni corretta, errore credenziali più chiaro.

**Novità 2.0.8:** fattura di riferimento apribile su ogni ricerca prodotto, report storico con tutti i fornitori, ricerca per parte di parola («bombo» trova «bombolino»), riconoscimento prodotti con Open Food Facts (alimentari e non), Ask Fatture completo con integrazione dalla centrale.

**Novità 2.0.7:** stato cache offline a colpo d’occhio (chip + scheda Dashboard, verifica completezza e ripresa automatica), errori Supabase con il motivo del server.
**Branch principale:** `main` (modifiche solo via branch + PR)
**Ultimo aggiornamento:** 30 ottobre 2026

### Completato

- archivio locale fatture con import XML FatturaPA, anteprima, duplicati, imponibile, IVA e totale;
- ricerca fatture, prodotti e fornitori con filtri e ordinamento per data, prezzo, fornitore, imponibile e totale;
- catalogo prodotti, classificazione conservativa e storico prezzi per fornitore;
- report storico con confronto prezzi, produttore/marca, unità normalizzate e stampa/PDF;
- recensioni separate per hotel, import MSG/EML/TXT, ranking, temi e alert;
- dashboard, report, destinazione fattura, backup, audit log e sincronizzazione centrale opzionale;
- login personale centrale con PIN e autorizzazione offline sul PC;
- tutti i profili condividono gli stessi permessi operativi; gestione utenti e PIN dall'area Sistema;
- Eye AI locale con Qwen/Ollama, agenti interni e fallback deterministico;
- GitHub Actions per test, build Windows e pubblicazione dell'installer su Supabase;
- controllo aggiornamenti da **Sistema → Aggiornamenti**, confronto con l'ultima versione pubblicata su Supabase e download dell'installer con verifica SHA-256;
- modalità offline: ricerche, dashboard e dettagli usano SQLite/cache locale quando Supabase o Internet non sono disponibili;
- ricerca dello storico prodotti con suggerimenti, selezione delle varianti e layout responsive a due colonne;
- gestione corretta degli errori Supabase: se il catalogo centrale non è raggiungibile, la schermata resta utilizzabile senza errore 500;
- parsing XML FatturaPA dei riepiloghi fiscali tramite `DatiRiepilogo`, con imponibile, IVA e totale coerenti;
- import PDF/TXT più affidabile e somma delle spese calcolata sulle righe pertinenti;
- profili centrali personali con cache del verificatore solo dopo un login online riuscito; modalità precedente disponibile esplicitamente per compatibilità.

### Verificato

- backend: `257 passed`;
- frontend: `npm test` 23 test passati e build Vite riuscita (verifiche del 30 ottobre 2026 sulla `2.0.44`);
- ricerca reale verificata con prodotti `pago` e `limoncello`;
- RPC Supabase del catalogo centrale verificata con risposta dati;
- build Windows locale pronta tramite `scripts\\build_windows.ps1`;
- `EyeSupremo.exe` come app a finestra nativa (WebView2), senza aprire il browser.

### Da completare

- il tag `v2.0.43` non è stato creato (il proxy della sandbox blocca i tag): l'installer viene comunque pubblicato dal workflow su push a `main` quando cambia `installer/EyeSupremo.iss`;
- sicurezza accessi: limitare i tentativi di login locale (oggi il blocco «Troppi tentativi» esiste solo nel percorso centrale);
- verificare su PC pulito: installazione, doppio clic → finestra app (non browser), primo login, import XML e aggiornamento;
- eventuali aggiornamenti futuri: firma digitale dell'installer e installazione automatica opzionale dopo conferma.

GitHub conserva codice e versioni, non fatture o recensioni reali. L'app controlla gli aggiornamenti su Supabase con la sessione centrale e scarica l'installer solo dopo richiesta dell'utente; l'installazione resta manuale e confermata.

## Hotel preconfigurati

- `gio` — Hotel Giò
- `choco` — Chocohotel
- `brigantino` — Hotel Il Brigantino

## Accesso e permessi

I profili sono condivisi su Supabase e usano username e PIN personali. Il primo
accesso su ogni PC richiede Internet; dopo la verifica l'accesso offline è
consentito per 7 giorni senza rinnovo automatico. Creazione utenti, cambio PIN e
disattivazione avvengono nel centrale e richiedono Internet. Il riavvio del PC
conserva il PIN scelto; nessun verificatore degli altri utenti viene scaricato.

Gli utenti `developer` e `supremo` mantengono gli stessi permessi operativi. Per le
recensioni ogni profilo vede tutti gli hotel, ma la visibilità delle recensioni si può
disattivare per singolo utente (permesso `can_view_reviews`, da **Utenti**); le fatture
restano nell'archivio unico Apice. Gli account precedentemente creati solo sul PC vanno registrati nel centrale.

**Attivazione:** prima di aggiornare i PC applicare la migrazione e distribuire le
funzioni descritte in [docs/CENTRAL_IDENTITY.md](docs/CENTRAL_IDENTITY.md). La modalità
locale precedente resta configurabile esplicitamente; la nuova autenticazione non
usa credenziali centrali condivise. README, docs e commit non devono contenere
credenziali reali o token.

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

**Importazione affidabile:** i voti con la virgola (`8,0`, `7,5`) sono accettati; un voto fuori scala (oltre 10 per Booking, oltre 5 per Google e TripAdvisor) viene scartato e la recensione è salvata senza voto, con avviso; un blocco difettoso non ferma le altre recensioni dello stesso file; una recensione identica (hotel, data, camera, fonte e testo) già presente non viene importata di nuovo e l'interfaccia indica quante sono state saltate. Il voto salvato resta visibile anche quando il testo non lo contiene.

**Recensioni solo voto:** una recensione senza testo scritto dall'ospite (solo il punteggio) conta nelle medie, nei voti per fonte e nei ranking, ma non viene mostrata come riga nell'archivio, nello storico e nelle segnalazioni anonime. Al suo posto compare un riquadro «Recensioni solo voto» con una voce per fonte e voto (es. «5 ★ su 10 · Booking · 3 recensioni»).

**Media camere:** nel menu Recensioni la voce **Media camere** è una pagina a sé con la media dei voti di ogni camera, **separata per fonte** e senza mescolare le scale: Booking su 10, Google e TripAdvisor su 5 (recensioni solo voto incluse). Per ogni fonte mostra media, numero di voti e minimo–massimo; in alto la media generale per fonte. Si filtra per hotel, si cerca per camera/hotel e si ordina per numero camera, media di una fonte o numero di voti. I voti fuori scala (es. 26 su Booking, causato da un giorno di calendario letto come voto) sono ignorati e segnalati con un avviso. Il calcolo è in `frontend/src/lib/roomAverages.ts` (test in `frontend/tests/roomAverages.test.ts`). **Filtro zona:** i gruppi "1/2/3/4 Cantine Wine" dell'Hotel Giò sono definiti in `frontend/src/lib/roomGroups.ts` (test in `frontend/tests/roomGroups.test.ts`); per cambiare i numeri di camera (zone e moquette) basta modificare quel file.

**Rilascio automatico dell'installer:** quando su `main` viene unita una modifica a `installer/EyeSupremo.iss` con una `AppVersion` non ancora pubblicata, il workflow *Publish Eye Supremo Windows Release* costruisce e pubblica da solo `EyeSupremo-Setup-<versione>.exe` nella GitHub Release `v<versione>`. Se quella versione esiste già non rifà la build. Resta avviabile a mano (Actions → Run workflow) o con un tag `v*`. Per rilasciare basta portare a `main` la nuova versione (package.json, backend, `installer/EyeSupremo.iss`, `docs/RELEASE_x_y_z.md`).

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

**Bootstrap dopo il login online:** dopo la verifica personale (con cache vuota o incompleta) Eye Supremo scarica in background fatture e recensioni da Supabase nella cache del PC. Poi offline consulta solo quella cache. Manuale: Impostazioni → Sincronizzazione → *Scarica tutto per offline*.

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

La replica centrale usa il token personale ottenuto dal login online; nessun PIN centrale condiviso viene usato nella nuova modalità. L'app continua a funzionare offline sui dati già replicati; il percorso legacy JWT resta opzionale per gli oggetti multi-hotel.

## Versione online (sola lettura, Vercel + Supabase)

Il frontend puo' essere pubblicato su **Vercel** (progetto `eye-supremo`, Root Directory `frontend`) e parlare direttamente con le Edge Functions Supabase `eye-identity` (login) e `eye-central-gateway` (dati), senza backend FastAPI. Si attiva con le variabili di build `VITE_EYE_BACKEND=supabase`, `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` (chiave pubblicabile, non segreta). Codice: `frontend/src/lib/supabaseDataService.ts`.

- **Disponibile**: login con profilo centrale (sessione 12 h) e elenco/ricerca fatture.
- **Anche online (sola lettura)**: dettaglio fattura, fornitori (elenco e scheda), prodotti (elenco e storico prezzi). Il frontend chiama direttamente le funzioni RPC di Supabase `eye_central_invoice_detail`, `eye_central_supplier_page`/`_detail`, `eye_central_product_page`/`_detail` con il token di sessione (nessuna nuova Edge Function). L'elenco prodotti online e' il catalogo centrale grezzo: le regole del backend Python (unione nomi, riconoscimento Open Food Facts, filtri) restano solo sul PC; unione/configurazione prodotti non sono disponibili online.
- **Utenti (online)**: pagina "Utenti" nel menu (profili centrali): crea utente, cambia PIN, disattiva/riattiva, tramite le azioni `list_users`/`create_user`/`set_pin`/`set_active` di `eye-identity`. Gli id numerici della UI sono l'ordine dell'elenco. Cambiare il PIN o disattivare un profilo revoca le sue sessioni (se e' il proprio, serve un nuovo accesso); l'ultimo profilo attivo non si puo' disattivare.
- **Recensioni (online)**: le recensioni centrali (`eye_central_review_page`, poche migliaia) si scaricano una volta per sessione e si calcolano nel browser con `frontend/src/lib/reviewsEngine.ts`, porta TypeScript di `review_importers.py` (pulizia testo, fonte/voto, identita') e `eye_services.py` (classificazione, ranking camere/servizi, andamento camere); il lessico e' in `reviewLexicon.ts` (generato da `eye_services.py`: **tenere allineati**). Come la cache del PC, non separa le email-digest in piu' recensioni (`split_review_blocks` non portato). Import file e invio a Supabase non sono disponibili online.
- **Non ancora online**: report storico prodotto, destinazione fattura, dashboard, report, storico, categorie, alert, salute dati, archivio file, import fatture, Ollama/IA.
- **Profili nel login**: online l'elenco dei profili (`supremo`, `sviluppatore`) e' fisso in `supabaseDataService.ts` e compare come suggerimenti e pulsanti sotto il nome utente; vanno aggiornati se si creano altri profili centrali.
- **Smartphone**: nella versione online il menu mostra solo Fatture; sotto i 760 px le tabelle con `data-label` diventano schede (CSS in fondo a `styles.css`), campi a 16 px (niente zoom su iOS), aree sicure (notch) e `manifest.webmanifest` per "Aggiungi a Home". Per avere le schede su una nuova tabella basta mettere `data-label` sulle `td`.
- **Navigazione smartphone (online)**: in testata c'e' l'interruttore **Fatture | Recensioni** (`.top-switch` in `Shell.tsx`); cambiando area si apre la **Home** (`OnlineHome.tsx`, pagina `home`): 4 riquadri a forme tonde/blob con i numeri chiave (Fatture: fatture, fornitori, prodotti, utenti; Recensioni: recensioni valide, voto medio, camera top, camera da migliorare), ognuno apre la sezione. La barra in basso e il Menu cambiano con l'area: Fatture = Home, Fatture, Fornitori, Prodotti, Menu (Utenti, Esci); Recensioni = Home, Panoramica, Ranking, Recensioni, Menu (Media camere, anonime, Ranking anonime, Storico). Online sono nascoste le voci non disponibili (Analisi IA, Recensioni online, Feedback, Impostazioni). Sottotitoli, selettore "Mostra" e selettore area della sidebar nascosti; ricerca fissa in alto. Testato a 320, 390 e 430 px.
- **Login**: i campi hanno `name`/`autocomplete` standard, quindi il gestore password del browser/telefono compila nome utente e PIN; l'ultimo nome utente usato viene ricordato sul dispositivo (mai il PIN). Su Chrome usa anche la Credential Management API (salva dopo l'accesso, precompila all'apertura) perche' il login non ricarica la pagina.
- **Sicurezza**: prima di esporre fatture reali, cambiare il PIN predefinito del profilo centrale (`EYESUPREMO_CENTRAL_USERNAME_OVERRIDE` / `EYESUPREMO_CENTRAL_PIN_OVERRIDE`).

## Avvio sviluppo

Requisiti: Python 3.11+ e Node 22.12+.

```powershell
setup.bat
start.bat
```

API locale compatibile: `http://127.0.0.1:8000/api/docs`. Il frontend usa la facciata versionata `/api/v1` per impostazione predefinita; in futuro può puntare a un servizio remoto impostando `VITE_EYE_API_URL` e `VITE_EYE_API_PREFIX` senza modificare il codice React.
UI dev: `http://127.0.0.1:5173`

## Installer Windows (app nativa)

Il PC finale **non deve avere Python o Node**. L'eseguibile è un'**app Windows a finestra** (WebView2), non una pagina aperta nel browser.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Lo script compila React, crea la cartella `dist/EyeSupremo/` (con `EyeSupremo.exe`) con PyInstaller (`--onedir --windowed` + pywebview) e incorpora la UI. Si usa la modalità cartella e non il file unico (`--onefile`) perché quest'ultimo si estrae in `%TEMP%` a ogni avvio e, se l'antivirus o Windows blocca l'estrazione, compare l'errore «Failed to load Python DLL … python312.dll». `installer/EyeSupremo.iss` con Inno Setup 6 produce `release/EyeSupremo-Setup.exe`.

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

La PR esegue automaticamente backend test + frontend test + frontend build, la scansione SkillSpector e la pipeline Windows genera l'installer (nome file `EyeSupremo-Setup-<versione>.exe`, versione da tenere allineata in `frontend/package.json`, `backend/app/main.py`, `backend/app/update_service.py` e `installer/EyeSupremo.iss`).

## Sicurezza

- dati reali locali per default;
- autenticazione locale con PIN e sessione (PIN con hash PBKDF2-SHA256, mai salvato in chiaro);
- ruolo ricavato dalla sessione, non accettato liberamente dal browser dopo la configurazione;
- hotel delle recensioni limitato ai permessi utente;
- agenti con strumenti dichiarati e limitati;
- sessioni database isolate per worker concorrente;
- Qwen non modifica direttamente fatture o prodotti;
- upload con limiti e nomi generati;
- hash duplicati;
- audit log;
- sync remota centrale con sessione personale revocabile e paginazione;
- nessun token reale committato.

## Limitazioni note

- il parser `.msg` usa euristiche sui digest reali e va affinato progressivamente sui formati di posta che incontriamo;
- le recensioni importate con le versioni fino alla 2.0.16 possono essere salvate come intera email in un unico record, con camera e voto sbagliati (es. un giorno della data letto come voto): le medie per camera ne risentono finché quei record non vengono reimportati o corretti;
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

### Credenziali centrali e variabili d'ambiente (modalità precedente)

Queste variabili sono usate soltanto con `EYESUPREMO_CENTRAL_IDENTITY_ENABLED=false`. Nella modalità centrale personale si usa il login, senza override condivisi.
Le vecchie variabili Windows `EYESUPREMO_CENTRAL_USERNAME` e `EYESUPREMO_CENTRAL_PIN` vengono ignorate (causavano «Credenziali non valide» dopo il ripristino del PIN predefinito). Per cambiare le credenziali centrali si usano `EYESUPREMO_CENTRAL_USERNAME_OVERRIDE` e `EYESUPREMO_CENTRAL_PIN_OVERRIDE`.
La sincronizzazione recensioni non invia più un checkpoint vuoto come data (errore «invalid input syntax for type timestamp»), e l'errore «Credenziali non valide» indica l'utente, senza esporre PIN o token.

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

### Ricerca a più parole («crostata marmellata»)

Con due o più parole la ricerca richiede **tutte** le parole (plurali e sinonimi inclusi: crostata≈crostate, marmellata≈marm≈confettura) e non si riduce più al solo sinonimo «marmellata». Così «crostata marmellata» riunisce in un solo prodotto crostata/crostate alla marmellata/crostate marmellate e non mostra più confetture, cornetti o dosatori. Una parola sola funziona come prima.

### Ricerca incompleta o lunga («crost», «crostate marmellate crostata»)

Mentre si scrive, o con 3+ parole, il testo non basta a capire il prodotto: la famiglia viene dedotta dalle voci trovate. Se almeno due voci (e metà del totale) sono nella stessa famiglia (es. «Crostate») si fondono in una sola, senza toccare le voci non imparentate. Funziona offline, senza Ollama: l'IA locale resta per la risposta di Ask, il raggruppamento dei nomi è deterministico (più veloce e ripetibile).

### Nomi equivalenti fusi anche nell'elenco catalogo

Anche senza ricerca (elenco catalogo, suggerimenti) le voci che sono lo stesso prodotto scritto in modo diverso diventano **una sola riga** con tutti i produttori: «crostata marmellata», «crostate alla marmellata», «crostate alle marmellate», «crostate marmellate». Si confrontano le parole utili senza articoli/preposizioni e senza desinenza (plurale/femminile), con «marm» = marmellata. Formati e misure restano nell'impronta (acqua 75x12 ≠ acqua 100x12) e si fondono solo voci della stessa famiglia riconosciuta. I nomi originali restano in `canonical_names` per storico e confronto fornitori.


### Materiali, sinonimi e famiglie (carta, plastica, marmellata…)

- **Materiali** (`carta`, `cartone`, `plastica`, `vetro`, `alluminio`, `legno`): la ricerca restituisce i prodotti *fatti* di quel materiale (carta igienica, bicchieri di carta, shopper, posate in plastica). Cibo e bevande solo *avvolti* o confezionati nel materiale («capocollo in carta», «caramelle in plastica») e i contributi CONAI restano esclusi. Un bicchiere di carta è quindi un prodotto di carta.
- **Parole in qualsiasi ordine e sinonimi**: «bombolone choco» e «choco bombolone» trovano gli stessi prodotti; `choco`, `cioccolato`, `ciocc`… e `bombolone`, `bomboloni`, `bombolino`… sono equivalenti. Le abbreviazioni dei fornitori (`marm`, `confet`, `ciocc`) valgono solo come parola intera (non `marm` ≠ marmo).
- **Famiglie**: «marmellata» trova anche `marm.`, `confettura`, `confet`, `conf extra`, ma non crostate, marmo o confetti.
- **Gusto e grammatura**: le varianti di una famiglia sono etichettate con gusto (arancia, fragola, frutti di bosco…) e contenuto della singola unità (`25gx100` = 25 g) e ordinate per gusto e poi grammatura (`backend/app/product_variants.py`). Le descrizioni originali non vengono mai modificate.

### Report storico: ricerca per marca e nome canonico

La ricerca del report storico trova una riga anche quando la parola cercata è nella **marca** o nel **nome canonico** del prodotto collegato, non solo nella descrizione scritta dal fornitore (es. «pago» trova «SUCCO ACE 200ML» se il prodotto è «Succo Pago Ace», marca Pago). Il controllo anti-collisione (`_row_matches_search` in `backend/app/report_service.py`) accetta la riga se la descrizione originale, quella normalizzata oppure marca + nome canonico corrispondono alla ricerca; le righe senza alcun legame con il prodotto cercato restano escluse. Test: `backend/tests/test_report_brand_and_canonical_match.py`.
