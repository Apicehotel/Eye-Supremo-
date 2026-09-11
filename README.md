# Eye Supremo

Eye Supremo è un applicativo **standalone, local-first e multi-hotel** per analizzare fatture, recensioni, camere, servizi, ranking e anomalie. Il PC resta pienamente operativo anche senza Internet; Supabase è un ponte opzionale per sincronizzare dati autorizzati tra Hotel Giò, Chocohotel e Hotel Il Brigantino.

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

Ogni documento sincronizzato mantiene hotel di origine e UUID.

## Ruoli

Eye Supremo crea cinque profili logici iniziali:

- **Sviluppatore**: accesso completo, configurazione e manutenzione.
- **Supremo**: lettura completa dei tre livelli/hotel e uso operativo globale.
- **Livello 1 / 2 / 3**: accesso operativo con esclusioni configurabili.

Per le fatture la regola è **visibilità generale con esclusioni**: categoria, prodotto, fornitore o parola chiave possono essere nascosti a un ruolo. Le stesse esclusioni vengono applicate alla ricerca e all'IA.

> Il selettore ruolo locale è un contesto operativo. La sincronizzazione remota richiede invece autenticazione Supabase JWT e membership server-side.

## Fatture

Import principale: **XML FatturaPA, TXT e PDF**.

Pipeline:

1. hash SHA-256 e controllo duplicati;
2. parsing e anteprima;
3. conferma esplicita;
4. classificazione righe;
5. voci contabili non utili all'analisi (`carburante`, sconti, abbuoni, bolli, trasporto, ecc.) restano nella fattura ma vengono escluse da ricerca prodotto/ranking;
6. indicizzazione FTS5;
7. confronto prezzi e creazione alert quando applicabile.

Le domande di spesa sommano **le righe pertinenti**, non il totale completo delle fatture che le contengono.

## Ricerca veloce

La ricerca è pensata per partire mentre si digita:

1. **SQLite FTS5** con prefix index (2/3/4 caratteri);
2. SQL filtrato;
3. **RapidFuzz** come fallback per errori e descrizioni simili;
4. Qwen solo per interpretazione finale.

La UI usa un debounce breve; l'effetto utente è una ricerca progressiva carattere per carattere.

## Recensioni

Ogni hotel carica il proprio archivio recensioni. Formati iniziali: **EML e TXT**.

Categorie storiche iniziali:

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

Le recensioni possono essere collegate alla camera. I temi non riconosciuti alimentano **Temi emergenti**: non diventano categorie al primo caso; vengono conteggiati e possono essere approvati dallo Sviluppatore.

## Ranking recensioni

Disponibili globalmente e per singolo hotel:

- Top 5 camere migliori;
- Top 5 camere peggiori;
- Top 5 servizi migliori;
- Top 5 servizi peggiori;
- Top/Bottom per Hotel Giò, Chocohotel e Brigantino.

Il ranking camere considera voto e quantità di recensioni, evitando che una singola recensione domini la classifica.

## Eye AI

Eye AI usa **Qwen 3 8B** tramite Ollama. Il modello riceve un contesto piccolo e citabile formato da:

- righe fattura pertinenti e relativo totale;
- recensioni pertinenti;
- camere;
- ranking migliori/peggiori.

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

Sul progetto **Apice MultiHotel** è previsto uno schema isolato:

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

Requisiti sulla macchina di sviluppo: Python 3.11+ e Node 20+.

```powershell
setup.bat
start.bat
```

API: `http://127.0.0.1:8000/api/docs`
UI dev: `http://127.0.0.1:5173`

## Installer Windows

Il PC finale **non deve avere Python o Node**.

Build su PC di sviluppo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Lo script:

1. compila React;
2. crea `dist/EyeSupremo.exe` con PyInstaller;
3. incorpora la UI nel backend.

Compilando poi `installer/EyeSupremo.iss` con Inno Setup 6 si ottiene `release/EyeSupremo-Setup.exe`.

I dati dell'installazione vengono salvati in `%LOCALAPPDATA%\EyeSupremo`, separati dall'eseguibile e quindi preservati dagli aggiornamenti.

## Test e CI

```powershell
cd backend
pytest -q
cd ..\frontend
npm ci
npm run build
```

La PR esegue automaticamente backend test + frontend build tramite GitHub Actions.

## Sicurezza

- dati reali locali per default;
- upload con limiti e nomi file generati;
- hash duplicati;
- audit log;
- sync remota con JWT obbligatorio;
- tabelle sync non accessibili direttamente ad `anon`/`authenticated`: passano dalla Edge Function;
- nessun token reale deve essere committato.

## Limitazioni note della milestone

- import recensioni diretto: EML/TXT; Outlook MSG richiede un parser/conversione dedicata prima di abilitarlo in produzione;
- il login Supabase desktop e il refresh automatico della sessione sono il passo successivo per rendere la sync utilizzabile dagli utenti finali senza configurazione manuale;
- l'indicizzazione semantica Qwen3 Embedding è predisposta come modello, mentre FTS5 + RapidFuzz sono il motore di ricerca attivo in questa milestone.
