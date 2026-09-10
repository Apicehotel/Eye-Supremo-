# Architettura RandFatture

RandFatture è un monolite modulare locale-first: React comunica con una API FastAPI su `localhost`; i documenti e SQLite rimangono nella cartella dati locale. I confini REST permettono in futuro di sostituire SQLite con PostgreSQL o collegare RandAI senza accoppiare i moduli.

## Moduli

- **Archivio**: fornitori, fatture, righe, prodotti canonici, alias e categorie.
- **Importazione**: rilevamento formato → estrazione → parsing → anteprima con confidenza → conferma esplicita.
- **Analisi**: prezzi normalizzati, storico, dashboard, anomalie e duplicati.
- **Ricerca**: SQL/FTS5 + fuzzy; Ollama interpreta la domanda solo quando disponibile e riceve esclusivamente record recuperati.
- **Operazioni**: impostazioni, log di audit e backup ZIP verificabile.

## Flusso import

Il file viene validato per estensione, dimensione e firma di base, salvato con nome generato e sottoposto a hash SHA-256. XML FatturaPA viene letto strutturalmente; i PDF nativi usano il testo incorporato. Immagini e PDF scansione usano Tesseract solo se installato. L'anteprima non scrive dati contabili: l'utente può correggere e confermare. Il controllo duplicati combina hash, numero/data/fornitore/importo.

## IA e RAG

La ricerca deterministica produce un piccolo contesto citabile. Se Ollama è attivo, il modello riceve domanda, schema delle intenzioni consentite e risultati; non riceve il database e non genera SQL libero. In assenza di Ollama vengono restituiti i risultati tradizionali. Le risposte includono sempre riferimenti a fattura, data, fornitore e riga.

## Decisioni

- FastAPI + SQLAlchemy 2 per API tipizzate e migrazione futura semplice.
- SQLite WAL, indici espliciti e paginazione; FTS5 è creato all'avvio.
- Elaborazioni di import predisposte come job; la milestone locale le esegue nel processo per ridurre complessità operativa.
- Nessun Electron nella prima versione: `start.bat` avvia browser, frontend e backend. Tauri è il candidato futuro per il packaging Windows.
