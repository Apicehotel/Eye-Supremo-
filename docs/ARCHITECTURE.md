# Architettura Eye Supremo

Eye Supremo è un monolite modulare **local-first** con API FastAPI, UI React e SQLite sul PC. Il confine REST permette di impacchettare tutto in un installer Windows mantenendo separati i moduli e predisponendo un ponte remoto Supabase senza rendere il cloud obbligatorio.

## Livelli

1. **Desktop/UI** — React compilato e incorporato nell'eseguibile Windows.
2. **API locale** — FastAPI su loopback (`127.0.0.1`).
3. **Dominio** — fatture, hotel, recensioni, camere, ranking, ruoli, alert, sync.
4. **Ricerca** — SQLite FTS5 + prefix index + SQL + RapidFuzz.
5. **IA** — Ollama/Qwen, utilizzato dopo il retrieval locale.
6. **Persistenza** — SQLite WAL in `%LOCALAPPDATA%\EyeSupremo` nel pacchetto Windows.
7. **Bridge remoto opzionale** — Supabase JWT + Edge Function + oggetti sincronizzati per hotel.

## Moduli backend

- `routers/api.py`: API legacy compatibile con la base RandFatture; da ridurre progressivamente.
- `routers/invoices_eye.py`: pipeline fatture Eye Supremo.
- `routers/eye.py`: hotel, ruoli, recensioni, ranking, IA, alert.
- `routers/sync_eye.py`: pull remoto autorizzato.
- `eye_services.py`: logica dominio.
- `search_index.py`: FTS5, ricerca incrementale e fuzzy fallback.
- `ai_service.py`: orchestrazione Qwen sui risultati recuperati.
- `sync_service.py`: adapter del bridge Supabase.

## Compatibilità database

La prima base RandFatture può già avere un SQLite con `suppliers`, `invoices`, `invoice_rows`, ecc. Per evitare migrazioni distruttive in questa fase, Eye Supremo aggiunge i nuovi concetti con tabelle collegate (`invoice_meta`, `invoice_row_policy`, `hotels`, `reviews`, `rooms`, ecc.) invece di rendere obbligatorie nuove colonne sulle tabelle esistenti.

## Import fatture

`XML/TXT/PDF → preview → conferma → invoice rows → policy riga → hotel metadata → FTS5 → alert`.

Le policy distinguono:

- `product`: entra in ricerca/prezzi/ranking;
- `accounting_excluded`: resta nel documento ma non entra nelle analisi prodotto;
- `review`: richiede verifica manuale.

Carburante, sconti e altre voci contabili note vengono escluse prima dell'analisi IA.

## Ricerca e Qwen

La ricerca live non chiama Qwen a ogni tasto. FTS5 usa prefix index e restituisce gli ID rilevanti; RapidFuzz interviene solo come fallback. Le somme sono calcolate dal database sulle righe risultanti.

Qwen riceve quindi un contesto limitato e strutturato. Questo evita il vecchio comportamento in cui il modello poteva dover leggere troppe righe e riduce drasticamente latenza e rischio di allucinazioni.

## Recensioni

`EML/TXT → hotel → camera opzionale → categorie note → polarity → temi emergenti → ranking`.

Le categorie storiche ChocoHotel sono seed iniziale. Un termine nuovo non crea immediatamente una categoria: entra in `emerging_themes`, accumula occorrenze e richiede approvazione Sviluppatore.

## Ranking

Due dimensioni principali:

- camere: Top/Bottom globale e per hotel;
- servizi/categorie: Top/Bottom globale e per hotel.

Il punteggio camera applica un fattore di confidenza basato sul numero di recensioni, così una camera con una sola recensione non domina la classifica.

## Ruoli

Profili logici: `developer`, `supremo`, `level1`, `level2`, `level3`.

Le fatture sono visibili di base; `role_exclusions` sottrae categorie, prodotti, fornitori o keyword non pertinenti. La ricerca IA applica le stesse esclusioni prima di costruire il contesto.

La selezione ruolo locale è utile per il client standalone. Qualsiasi accesso remoto usa JWT Supabase e membership server-side.

## Supabase bridge

Il bridge non è il database primario. `eye_sync_objects` conserva oggetti sincronizzati con `hotel_code`, `entity_type`, UUID e payload JSON. `eye_sync_memberships` definisce gli hotel autorizzati e la lettura globale.

La Edge Function `eye-supremo-sync` ha `verify_jwt=true`; usa la membership per autorizzare push/pull e il service role solo internamente. Le tabelle non sono esposte direttamente ai ruoli `anon` e `authenticated`.

## Packaging Windows

La UI viene compilata in `frontend/dist` e incorporata con PyInstaller nel backend. `desktop.py` avvia Uvicorn su `127.0.0.1:8765` e apre il browser. Inno Setup produce l'installer finale.

La macchina finale non richiede Python o Node. I dati sono persistenti in LocalAppData, separati dall'eseguibile.

## Evoluzione senza parti zombie

La API legacy resta temporaneamente per compatibilità, ma le nuove funzionalità vivono nei router modulari. Quando tutte le schermate usano le API `/api/eye/*`, il router legacy può essere ridotto alle sole API ancora necessarie e infine rimosso in una PR dedicata, dopo test di regressione.
