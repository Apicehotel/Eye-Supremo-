# Eye Supremo — guida per agenti (Claude, Cursor, GPT/Codex)

Questo file è l'unica fonte delle regole di lavoro condivise. `CLAUDE.md` e `.cursor/rules/` lo richiamano.
Lo stato corrente del lavoro e i passaggi di consegna stanno in `docs/HANDOFF.md`.

## Il progetto in breve
Gestionale locale-first: backend FastAPI + SQLAlchemy/SQLite (`backend/`), frontend React + TypeScript + Vite (`frontend/`),
bridge Supabase (schema `eye_supremo`), installer Windows (`installer/`, PyInstaller + Inno Setup). Descrizione completa: `README.md`.

## Regole non negoziabili
1. **Mai segreti** (PIN, password, token, chiavi S3/API) in codice, README, commit, PR, chat o log. Solo secrets di GitHub / variabili d'ambiente.
2. **README sempre aggiornato** a ogni modifica di comportamento: un altro strumento deve capire l'app leggendolo.
3. Non cambiare le descrizioni originali delle fatture: le etichette (gusto, grammatura…) sono solo calcolate per la lettura.
4. Non eseguire scritture su Supabase di produzione senza richiesta esplicita dell'utente (SQL solo in lettura per le analisi).

## Come si lavora insieme (per evitare conflitti)
- **Un solo agente per volta su un'area.** Prima di iniziare leggi `docs/HANDOFF.md`, scrivi in «In corso» cosa tocchi (file/area) e il tuo nome.
- **Un ramo per agente e per compito**: `feat/…`, `fix/…`, `docs/…`. Mai commit diretti su `main`.
- Fai PR piccole e frequenti su `main`; prima di aprirla fai `git fetch && git rebase origin/main` (o merge) e rilancia i test.
- Non riscrivere o riformattare file che non stai modificando. Niente refactor misti a correzioni.
- Finito il compito: sposta la voce in «Fatto» di `docs/HANDOFF.md` con una riga (cosa, PR, eventuali punti aperti).
- Se due agenti hanno bisogno della stessa area: il secondo aspetta o lavora su un'altra; in caso di dubbio chiedi all'utente.

## Verifiche prima di ogni PR
```
cd backend && python -m pytest -q          # suite completa (~2,5 min); in CI gira da sola
cd frontend && npx tsc --noEmit && npm test && npm run build
```
Nuovo comportamento = nuovo test. Non dichiarare «fatto» senza aver eseguito i test.

## Versione e rilascio
- La versione compare in: `frontend/package.json` (+ `package-lock.json`, prime due occorrenze), `backend/app/main.py`, `backend/app/update_service.py`,
  `installer/EyeSupremo.iss` (testata, `AppVersion`, `OutputBaseFilename`, `VersionInfoVersion`), `README.md`. Un test controlla che coincidano.
- Il workflow «Publish Eye Supremo Windows Release» parte su push a `main` che modifica `installer/EyeSupremo.iss` (o su tag `v*`),
  costruisce l'installer e lo pubblica su Supabase (`eye-updates`, `latest.json`). I secrets S3 sono nei *Repository secrets* di GitHub.
- Release = bump versione + PR + merge + verifica che il workflow sia verde. Le sandbox cloud non possono creare tag: se serve il tag, lo crea l'utente.

## Ricerca prodotti (area delicata)
Regole in `backend/app/product_taxonomy.py` (alias, famiglie, materiali), `product_recognition.py`, `product_variants.py` (gusto/grammatura).
Materiali: «carta», «plastica»… = prodotti fatti di quel materiale, non cibo avvolto. Parole in qualsiasi ordine, sinonimi e abbreviazioni
(`marm`, `ciocc`) solo come parola intera. Ogni regola nuova va provata su nomi reali del catalogo e coperta da test.
