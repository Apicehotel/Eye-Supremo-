# Eye Supremo

Eye Supremo è un applicativo **standalone, local-first e multi-hotel** per analizzare fatture, recensioni, camere, servizi, ranking, storico prezzi e anomalie. Il PC resta pienamente operativo anche senza Internet; Supabase è un ponte opzionale per sincronizzare dati autorizzati tra Hotel Giò, Chocohotel e Hotel Il Brigantino.

## Principi

- **PC = motore principale**: SQLite, import, ricerca, ranking, backup e IA locale.
- **GitHub = codice e versioni**: mai fatture o recensioni reali.
- **Supabase = ponte opzionale**: sync autenticata push/pull, separata dal funzionamento locale.
- **Ollama/Qwen = IA locale**: interpreta dati già recuperati; non rilegge l'intero archivio a ogni domanda.
- **Freeze main**: modifiche generate da agenti solo su branch + PR + revisione umana.

## Hotel preconfigurati

- `gio` — Hotel Giò
- `choco` — Chocohotel
- `brigantino` — Hotel Il Brigantino

## Accesso e ruoli

Eye Supremo usa autenticazione locale con PIN e sessione. Al primo avvio lo Sviluppatore imposta il PIN; successivamente gli utenti accedono con il proprio profilo.

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

## Recensioni

Le recensioni sono divise per hotel. Prima si seleziona **Giò / Choco / Brigantino**, poi si caricano i file: tutte le recensioni estratte ereditano l'hotel scelto.

Formati supportati:

- **Outlook `.msg`**;
- EML;
- TXT.

Un singolo `.msg` può contenere **più recensioni**: il parser separa i blocchi, prova a riconoscere Booking/Google/TripAdvisor, camera, data, voto e testo, e crea più record dallo stesso messaggio. Messaggi che non sembrano recensioni vengono segnalati invece di essere importati alla cieca.

Categorie iniziali:

- Camere / Arredi
- Ristorante
- Colazione
- Staff
- Letti
- Pulizia
- Altro
- Parcheggio
- Posizione
- Cuscini

Le recensioni possono essere collegate alla camera. I temi non riconosciuti alimentano **Temi emergenti** e possono essere approvati dallo Sviluppatore.

## Ranking recensioni

Disponibili globalmente per Supremo/Sviluppatore e per singolo hotel:

- Top 5 camere migliori;
- Top 5 camere peggiori;
- Top 5 servizi migliori;
- Top 5 servizi peggiori.

## Eye AI

Eye AI usa **Qwen 3 8B** tramite Ollama. Il modello riceve un contesto piccolo formato da righe fattura pertinenti, recensioni, camere e ranking.

La chiamata Ollama usa **structured output JSON Schema**: Qwen deve restituire `answer`, `facts` e `confidence`, riducendo risposte libere/non verificabili. Se Ollama non è disponibile, il sistema ricade sul motore deterministico locale.

Modelli consigliati:

```text
qwen3:8b
llama3.2:3b
qwen3-embedding:0.6b
```

Eseguire `scarica-modelli-ia.bat` dopo aver installato Ollama.

## Alert

Il dominio supporta alert persistenti per prezzo/anomalie. La pipeline fatture può generare alert quando il prezzo corrente supera in modo rilevante lo storico. Le righe contabili escluse non generano alert prodotto.

## Ponte Supabase

Sul progetto **Apice MultiHotel** sono presenti:

- `eye_sync_memberships`
- `eye_sync_objects`
- Edge Function `eye-supremo-sync`

L'Edge Function richiede JWT valido. `developer` e `supremo` possono essere configurati per lettura globale; gli altri utenti ricevono solo gli hotel autorizzati dalla membership server-side.

Variabili locali in `.env.example`:

```text
EYESUPREMO_SYNC_ENABLED=false
EYESUPREMO_SUPABASE_URL=
EYESUPREMO_SUPABASE_PUBLISHABLE_KEY=
EYESUPREMO_SUPABASE_ACCESS_TOKEN=
```

La sync è **disattivata per default** e l'app continua a funzionare offline.

## Avvio sviluppo

Requisiti: Python 3.11+ e Node 20+.

```powershell
setup.bat
start.bat
```

API: `http://127.0.0.1:8000/api/docs`
UI dev: `http://127.0.0.1:5173`

## Installer Windows

Il PC finale **non deve avere Python o Node**.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Lo script compila React, crea `dist/EyeSupremo.exe` con PyInstaller e incorpora la UI nel backend. `installer/EyeSupremo.iss` con Inno Setup 6 produce `release/EyeSupremo-Setup.exe`.

I dati vengono salvati in `%LOCALAPPDATA%\EyeSupremo`, separati dall'eseguibile.

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
- upload con limiti e nomi generati;
- hash duplicati;
- audit log;
- sync remota con JWT obbligatorio;
- nessun token reale committato.

## Limitazioni note

- il parser `.msg` usa euristiche sui digest reali e va affinato progressivamente sui formati di posta che incontriamo;
- il login Supabase desktop e refresh automatico della sessione restano necessari per rendere la sync remota completamente trasparente agli utenti;
- `qwen3-embedding:0.6b` è predisposto, mentre FTS5 + RapidFuzz sono ancora il motore di retrieval attivo.
