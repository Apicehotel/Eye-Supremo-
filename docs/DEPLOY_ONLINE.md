# Eye Supremo online (hosting opzionale)

Eye Supremo nasce **local-first** sul PC Windows e quella resta la modalita' principale. Questa guida spiega come ospitarlo anche online (telefono, altri PC) con un container Docker.

## Come funziona

Un solo container esegue l'API FastAPI e serve anche il frontend gia' compilato (`frontend/dist`) sulla **stessa origine**: niente CORS e niente `VITE_EYE_API_URL`. Il `Dockerfile` e' nella radice del repo.

- Porta: `8000`. Controllo di salute: `GET /api/health`.
- Dati (SQLite, upload, backup, recensioni): cartella `/data`, **da montare come volume persistente**. Senza volume i dati si perdono a ogni redeploy.
- Una sola istanza e un solo worker: SQLite in WAL e le cache in memoria non vanno condivisi tra repliche.
- Dipendenze server in `backend/requirements-server.txt` (come `requirements.txt` senza `pywebview` e senza i pacchetti di test).

## Deploy su un host Docker (per esempio Coolify)

1. Nuova applicazione dal repo GitHub `Apicehotel/Eye-Supremo-`, branch `main`, **Build Pack: Dockerfile**.
2. Porta esposta `8000`, dominio con HTTPS.
3. Aggiungi un **volume persistente** montato su `/data`.
4. Variabili d'ambiente (tutte con prefisso `EYESUPREMO_`, vedi `.env.example`):
   - `EYESUPREMO_SYNC_ENABLED=true` solo se si usa il ponte Supabase;
   - `EYESUPREMO_CACHE_BOOTSTRAP_ON_START=true|false` (scarica fatture e recensioni dal centrale all'avvio);
   - `EYESUPREMO_MAX_UPLOAD_MB` se serve alzare il limite di upload;
   - `EYESUPREMO_OLLAMA_URL` solo se esiste un Ollama raggiungibile dal server (vedi Limiti).
5. Distribuisci e apri `https://<dominio>/api/health`: deve rispondere 200.

Prova in locale:

```bash
docker build -t eye-supremo .
docker run --rm -p 8000:8000 -v eye-data:/data eye-supremo
```

## Variante: frontend su Vercel, backend altrove

Possibile ma piu' fragile (due indirizzi, CORS). Progetto Vercel:

- **Root Directory**: `frontend`
- Variabile `VITE_EYE_API_URL` = indirizzo pubblico del backend (senza slash finale)
- Sul backend `EYESUPREMO_CORS_ORIGINS` deve contenere il dominio Vercel, separati da virgola e senza slash finale.

Il backend va comunque ospitato da qualche parte: Vercel non esegue FastAPI con SQLite persistente.

## Sicurezza (leggere prima di pubblicare)

- Online, fatture e recensioni reali sono raggiungibili da Internet. L'unica protezione e' il login dell'app: **usa sempre HTTPS** e non lasciare **PIN banali o predefiniti** sui profili. Il PIN predefinito del profilo centrale e' pubblico (e' nel codice del repo): va cambiato prima di esporre l'app, con le variabili `EYESUPREMO_CENTRAL_USERNAME_OVERRIDE` e `EYESUPREMO_CENTRAL_PIN_OVERRIDE`.
- Valuta di mettere l'host dietro un'ulteriore protezione (accesso a elenco di IP, VPN o proxy con autenticazione).
- Nessun dato reale su GitHub: i dati restano solo nel volume `/data`.
- Fai **backup del volume** `/data` (contiene l'intero database).
- Non scrivere PIN, chiavi o token in questo file, nei commit o nel README.

## Limiti

- **IA locale (Ollama/Qwen)**: non e' nel container. Senza `EYESUPREMO_OLLAMA_URL` valido, Ask mostra il messaggio esplicito e ricade sul riepilogo SQLite deterministico.
- **Aggiornamenti dell'installer Windows**: non riguardano la versione online.
- Il lavoro offline del PC resta indipendente: la versione online non lo sostituisce.
