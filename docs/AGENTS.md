# Eye Supremo · Agenti interni

## Obiettivo

Dividere il lavoro di Qwen in specialisti piccoli, verificabili e con strumenti limitati. I calcoli restano deterministici; Qwen interpreta e sintetizza.

## Flusso

`router → specialisti necessari → verifier → answer`

**Ask Fatture** usa `area=invoices` (solo prodotti/prezzi/fatture). **Ask Recensioni** usa `area=reviews`. `area=all` resta per domande miste.

Gli specialisti dati possono lavorare in parallelo ma ogni worker apre una sessione SQLAlchemy/SQLite indipendente.

## Agenti

- `products`: prodotto canonico, alias, ricerca e storico.
- `classifier`: Food & Beverage / Non Food e sottocategorie.
- `invoices`: fatture e fornitori.
- `prices`: storico, media, minimo, ultimo prezzo e variazioni.
- `reviews`: recensioni, camere, servizi e ranking.
- `verifier`: unità compatibili, collisioni semantiche e warning.
- `answer`: risposta finale JSON strutturata.

## Layer mirror IA

`SQLite (deterministico) → llama3.2:3b (veloce) → qwen3:8b (qualità)`

- Policy default `fast_first`: su Ask, `llama3.2:3b` prova per primo; se la risposta è vuota o `confidence=low` scala a `qwen3:8b`.
- `fast_only` evita del tutto il modello 8B.
- `quality` forza il modello qualità quando disponibile.
- I calcoli restano sempre deterministici; i layer LLM sintetizzano solo il contesto già recuperato.
- Se Ollama non è avviato o mancano i modelli, Ask mostra un messaggio esplicito e ricade sul riepilogo SQLite.

## Regole

- Nessun agente modifica direttamente fatture o prodotti tramite il canale di risposta.
- `bombolone` e `bombola` non sono equivalenti anche se simili lessicalmente.
- I prezzi vengono confrontati solo su unità normalizzate compatibili.
- Se Ollama non risponde, il fallback deterministico continua a funzionare offline.
- Le PR degli agenti vengono validate da CI e build Windows anche quando puntano alla branch `feat/eye-supremo-foundations`.
