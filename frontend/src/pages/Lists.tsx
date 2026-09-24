import {useEffect, useState} from 'react';
import {Boxes, Download, ChevronRight, FilePenLine, Cloud} from 'lucide-react';
import {api, euro, shortDate} from '../lib/api';
import {Empty, Loading, PageHeader, SearchBox, Status} from '../components/UI';

type InvoiceRow = {
  id: number | string;
  source?: 'local' | 'central' | 'both';
  openable?: boolean;
  numero: string;
  data?: string | null;
  supplier?: {ragione_sociale?: string};
  row_count?: number | null;
  imponibile?: number | null;
  iva?: number | null;
  totale?: number | null;
  stato_importazione?: string;
};

type UnifiedPayload = {
  items: InvoiceRow[];
  local_count?: number;
  central_count?: number;
  central_total?: number | null;
  central_configured?: boolean;
  central_error?: string | null;
};

function sourceLabel(source?: string) {
  if (source === 'central') return 'Supabase';
  if (source === 'both') return 'PC + Supabase';
  return 'PC';
}

function sourceTone(source?: string): 'ok' | 'warn' | undefined {
  if (source === 'central') return 'warn';
  return 'ok';
}

export function Invoices({onOpen}: {onOpen?: (id: number) => void}) {
  const [payload, setPayload] = useState<UnifiedPayload | null>(null);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  const [warehouseBusy, setWarehouseBusy] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    const t = setTimeout(() => {
      setError('');
      api<UnifiedPayload | InvoiceRow[]>(`/invoices?q=${encodeURIComponent(q)}&include_central=true`)
        .then((x) => {
          if (!active) return;
          if (Array.isArray(x)) setPayload({items: x});
          else setPayload(x);
        })
        .catch(() => {
          if (active) {
            setPayload({items: []});
            setError('Impossibile caricare le fatture. Verifica che il backend sia attivo.');
          }
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [q]);

  async function loadWarehouse(id: number) {
    setWarehouseBusy(id);
    setError('');
    try {
      const r: any = await api(`/warehouse/from-invoice/${id}`, {method: 'POST'});
      alert(`Magazzino aggiornato: ${r.created} movimenti creati, ${r.skipped} righe saltate.`);
    } catch (e: any) {
      setError(e.message || 'Impossibile caricare la fattura in magazzino');
    } finally {
      setWarehouseBusy(null);
    }
  }

  const items = payload?.items;
  const subtitleParts = ['Archivio PC'];
  if (payload?.central_configured) {
    subtitleParts.push(
      payload.central_total != null
        ? `Supabase ${Number(payload.central_total).toLocaleString('it-IT')}`
        : 'Supabase collegato',
    );
  } else {
    subtitleParts.push('Supabase non configurato (.env)');
  }

  return (
    <>
      <PageHeader title="Fatture" subtitle={subtitleParts.join(' · ')}>
        <SearchBox value={q} onChange={setQ} placeholder="Numero o fornitore…" />
      </PageHeader>
      {payload?.central_error && (
        <div className="warning" style={{margin: '0 0 12px'}}>
          Catalogo Supabase: {payload.central_error}
        </div>
      )}
      <section className="panel list-panel">
        {error ? (
          <div className="empty">
            <b>{error}</b>
          </div>
        ) : !items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Numero</th>
                  <th>Data</th>
                  <th>Fornitore</th>
                  <th>Fonte</th>
                  <th>Prodotti</th>
                  <th>Imponibile</th>
                  <th>IVA</th>
                  <th>Totale</th>
                  <th>Stato</th>
                  <th aria-label="Azioni" />
                </tr>
              </thead>
              <tbody>
                {items.map((i) => {
                  const localId = typeof i.id === 'number' ? i.id : null;
                  const canOpen = i.openable !== false && localId != null;
                  return (
                    <tr key={String(i.id)}>
                      <td>
                        <b>{i.numero}</b>
                      </td>
                      <td>{i.data ? shortDate(i.data) : '—'}</td>
                      <td>{i.supplier?.ragione_sociale || '—'}</td>
                      <td>
                        <Status tone={sourceTone(i.source)}>
                          {i.source === 'central' ? <Cloud size={12} style={{marginRight: 4}} /> : null}
                          {sourceLabel(i.source)}
                        </Status>
                      </td>
                      <td>{i.row_count ?? '—'}</td>
                      <td>{i.imponibile != null ? euro(i.imponibile) : '—'}</td>
                      <td>{i.iva != null ? euro(i.iva) : '—'}</td>
                      <td>
                        <b>{i.totale != null ? euro(i.totale) : '—'}</b>
                      </td>
                      <td>
                        <Status>{i.stato_importazione || '—'}</Status>
                      </td>
                      <td>
                        <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                          {canOpen ? (
                            <>
                              <button
                                className="secondary-btn"
                                onClick={() => onOpen?.(localId!)}
                                title="Apri nell'editor"
                              >
                                <FilePenLine size={16} />
                                Apri
                              </button>
                              <button
                                className="secondary-btn"
                                disabled={warehouseBusy === localId}
                                onClick={() => loadWarehouse(localId!)}
                                title="Carica i prodotti collegati in magazzino"
                              >
                                <Boxes size={16} />
                                {warehouseBusy === localId ? 'Carico…' : 'Magazzino'}
                              </button>
                            </>
                          ) : (
                            <small style={{opacity: 0.75}}>Solo metadati Supabase</small>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty />
        )}
      </section>
    </>
  );
}

export function Products() {
  const [items, setItems] = useState<any[]>(),
    [q, setQ] = useState('');
  useEffect(() => {
    api<any[]>(`/products?q=${encodeURIComponent(q)}`).then(setItems);
  }, [q]);
  return (
    <>
      <PageHeader title="Prodotti" subtitle="Prodotti canonici, prezzi e storico">
        <SearchBox value={q} onChange={setQ} placeholder="Nome, marca o codice…" />
      </PageHeader>
      <section className="panel list-panel">
        {!items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome canonico</th>
                  <th>Categoria</th>
                  <th>Marca</th>
                  <th>Acquisti</th>
                  <th>Minimo</th>
                  <th>Media</th>
                  <th>Massimo</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <b>{p.nome_canonico}</b>
                    </td>
                    <td>{p.categoria || '—'}</td>
                    <td>{p.marca || '—'}</td>
                    <td>{p.purchases}</td>
                    <td>{p.min_price ? euro(p.min_price) : '—'}</td>
                    <td>{p.avg_price ? euro(p.avg_price) : '—'}</td>
                    <td>{p.max_price ? euro(p.max_price) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Nessun prodotto canonico" text="I prodotti possono essere creati e collegati alle righe fattura." />
        )}
      </section>
    </>
  );
}

export function Suppliers() {
  const [items, setItems] = useState<any[]>(),
    [q, setQ] = useState('');
  useEffect(() => {
    api<any[]>(`/suppliers?q=${encodeURIComponent(q)}`).then(setItems);
  }, [q]);
  return (
    <>
      <PageHeader title="Fornitori" subtitle="Anagrafiche e storico commerciale">
        <SearchBox value={q} onChange={setQ} placeholder="Ragione sociale o P. IVA…" />
      </PageHeader>
      <section className="panel list-panel">
        {!items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ragione sociale</th>
                  <th>Partita IVA</th>
                  <th>Codice fiscale</th>
                  <th>Email</th>
                  <th>Telefono</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <b>{s.ragione_sociale}</b>
                    </td>
                    <td>{s.partita_iva || '—'}</td>
                    <td>{s.codice_fiscale || '—'}</td>
                    <td>{s.email || '—'}</td>
                    <td>{s.telefono || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty />
        )}
      </section>
    </>
  );
}

export function Reports() {
  return (
    <>
      <PageHeader title="Report" subtitle="Analisi deterministiche ed esportazioni">
        <a className="primary-btn" href="/api/reports/spending.csv">
          <Download size={17} />
          Esporta CSV
        </a>
      </PageHeader>
      <section className="report-grid">
        {[
          'Spesa per mese',
          'Spesa per anno',
          'Spesa per fornitore',
          'Spesa per categoria',
          'Prodotti più acquistati',
          'Aumento prezzi',
          'Confronto fornitori',
          'Duplicati e anomalie',
        ].map((x) => (
          <article className="panel report" key={x}>
            <div>
              <b>{x}</b>
              <span>Apri analisi dettagliata</span>
            </div>
            <ChevronRight />
          </article>
        ))}
      </section>
    </>
  );
}

export function HistoryPage() {
  const [items, setItems] = useState<any[]>();
  useEffect(() => {
    api<any[]>('/history').then(setItems);
  }, []);
  return (
    <>
      <PageHeader title="Storico" subtitle="Esplorazione temporale degli acquisti" />
      <section className="timeline">
        {!items ? (
          <Loading />
        ) : items.length ? (
          items.map((x) => (
            <article className="year" key={x.year}>
              <div className="year-dot" />
              <strong>{x.year}</strong>
              <div className="panel year-panel">
                <span>{x.invoices} fatture</span>
                <b>{euro(x.total)}</b>
                <small>{x.suppliers} fornitori</small>
              </div>
            </article>
          ))
        ) : (
          <Empty />
        )}
      </section>
    </>
  );
}

export function SimplePage({title, subtitle}: {title: string; subtitle: string}) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <section className="panel list-panel">
        <Empty title={`${title} pronto`} text="La struttura è disponibile e si popolerà con i dati dell'archivio." />
      </section>
    </>
  );
}
