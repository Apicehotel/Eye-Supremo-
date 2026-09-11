# Eye Supremo · Agenti interni

## Obiettivo

Dividere il lavoro di Qwen in specialisti piccoli, verificabili e con strumenti limitati. I calcoli restano deterministici; Qwen interpreta e sintetizza.

## Flusso

`router → specialisti necessari → verifier → answer`

Gli specialisti dati possono lavorare in parallelo ma ogni worker apre una sessione SQLAlchemy/SQLite indipendente.

## Agenti

- `products`: prodotto canonico, alias, ricerca e storico.
- `classifier`: Food & Beverage / Non Food e sottocategorie.
- `invoices`: fatture e fornitori.
- `prices`: storico, media, minimo, ultimo prezzo e variazioni.
- `reviews`: recensioni, camere, servizi e ranking.
- `verifier`: unità compatibili, collisioni semantiche e warning.
- `answer`: risposta finale JSON strutturata.

## Regole

- Nessun agente modifica direttamente fatture o prodotti tramite il canale di risposta.
- `bombolone` e `bombola` non sono equivalenti anche se simili lessicalmente.
- I prezzi vengono confrontati solo su unità normalizzate compatibili.
- Se Ollama non risponde, il fallback deterministico continua a funzionare offline.
