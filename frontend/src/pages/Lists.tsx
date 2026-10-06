import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Download, ChevronRight, Bell, Search } from "lucide-react";
import { api, eyeApi, euro, shortDate } from "../lib/api";
import {
  Empty,
  Loading,
  PageHeader,
  SearchBox,
  Status,
} from "../components/UI";
import { Page } from "../components/Shell";
import { HistoricalReportPage } from "./HistoricalReport";

type SortDirection = "asc" | "desc";
type SortKey = string;

function sortIndicator(sort: {key: SortKey; direction: SortDirection}, key: SortKey) {
  return sort.key === key ? (sort.direction === "asc" ? " ↑" : " ↓") : "";
}

function compareValues(left: unknown, right: unknown, direction: SortDirection) {
  if (left == null || left === "") return right == null || right === "" ? 0 : 1;
  if (right == null || right === "") return -1;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const numeric = typeof left === "number" || typeof right === "number" || (!Number.isNaN(leftNumber) && !Number.isNaN(rightNumber));
  const result = numeric
    ? leftNumber - rightNumber
    : String(left).localeCompare(String(right), "it", {numeric: true, sensitivity: "base"});
  return direction === "asc" ? result : -result;
}

function SortHeader({label, sort, sortKey, onSort}: {label: string; sort: {key: SortKey; direction: SortDirection}; sortKey: SortKey; onSort: (key: SortKey) => void}) {
  return <button type="button" className="table-sort-button" onClick={() => onSort(sortKey)}>{label}{sortIndicator(sort, sortKey)}</button>;
}

export function Invoices() {
  const [items, setItems] = useState<any[]>(),
    [live, setLive] = useState<any>(),
    [remote, setRemote] = useState<any>(),
    [q, setQState] = useState(""),
    [page, setPage] = useState(0),
    [pageSize, setPageSize] = useState(50),
    [detail, setDetail] = useState<any>(),
    [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "data", direction: "desc"});
  const setQ = (value: string) => {
    setPage(0);
    setQState(value);
    setDetail(undefined);
  };
  const changePageSize = (value: number) => {
    setPage(0);
    setPageSize(value);
    setDetail(undefined);
  };
  async function openDetail(sourceHash: string) {
    try {
      setDetail(await eyeApi<any>(`/central/invoices/${encodeURIComponent(sourceHash)}`));
    } catch {
      setDetail({ error: "Dettaglio non disponibile" });
    }
  }
  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim()) {
        Promise.all([
          eyeApi<any>(`/search/live?q=${encodeURIComponent(q)}&limit=${pageSize}`),
          eyeApi<any>(`/central/invoices?q=${encodeURIComponent(q)}&limit=${pageSize}`),
        ])
          .then(([local, central]) => {
            setLive(local);
            setRemote(central);
          })
          .catch(() => {
            setLive(undefined);
            setRemote(undefined);
          });
      } else {
        setLive(undefined);
        Promise.all([
          api<any[]>(`/invoices`),
          eyeApi<any>(`/central/invoices?limit=${pageSize}&offset=${page * pageSize}`),
        ])
          .then(([local, central]) => {
            setItems(local);
            setRemote(central);
          })
          .catch(() => setRemote(undefined));
      }
    }, 180);
    return () => clearTimeout(t);
  }, [q, page, pageSize]);
  const centralHasRows = Boolean(
    remote?.items?.some((r: any) => r.original_description != null),
  );
  const toggleSort = (key: SortKey) => setSort((current) => current.key === key ? {key, direction: current.direction === "asc" ? "desc" : "asc"} : {key, direction: key === "data" ? "desc" : "asc"});
  const sortedLocalItems = useMemo(() => [...(items || [])].sort((a, b) => compareValues(
    sort.key === "fornitore" ? a.supplier?.ragione_sociale : a[sort.key],
    sort.key === "fornitore" ? b.supplier?.ragione_sociale : b[sort.key],
    sort.direction,
  )), [items, sort]);
  const sortedRemoteItems = useMemo(() => [...(remote?.items || [])].sort((a, b) => compareValues(
    sort.key === "data" ? a.invoice_date : sort.key === "fornitore" ? a.supplier_name : sort.key === "totale" ? (a.total ?? a.line_total) : sort.key === "imponibile" ? a.taxable : sort.key === "iva" ? a.vat : sort.key === "numero" ? a.invoice_number : sort.key === "prezzo" ? a.unit_price : a.original_description,
    sort.key === "data" ? b.invoice_date : sort.key === "fornitore" ? b.supplier_name : sort.key === "totale" ? (b.total ?? b.line_total) : sort.key === "imponibile" ? b.taxable : sort.key === "iva" ? b.vat : sort.key === "numero" ? b.invoice_number : sort.key === "prezzo" ? b.unit_price : b.original_description,
    sort.direction,
  )), [remote?.items, sort]);
  const sortedLiveItems = useMemo(() => [...(live?.results || [])].sort((a, b) => compareValues(
    sort.key === "data" ? a.date : sort.key === "fornitore" ? a.supplier : sort.key === "totale" ? a.row_total : sort.key === "prezzo" ? a.unit_price : sort.key === "numero" ? a.invoice : a.description,
    sort.key === "data" ? b.date : sort.key === "fornitore" ? b.supplier : sort.key === "totale" ? b.row_total : sort.key === "prezzo" ? b.unit_price : sort.key === "numero" ? b.invoice : b.description,
    sort.direction,
  )), [live?.results, sort]);
  return (
    <>
      <PageHeader
        title="Fatture"
        subtitle="Archivio locale + archivio centrale Supabase"
      >
        <div className="list-header-controls"><div className="list-header-main">
          <SearchBox
            value={q}
            onChange={setQ}
            placeholder="Cerca prodotto, fornitore, fattura…"
          />
          <label className="page-size-control" style={{ height: 42, display: "flex", alignItems: "center", gap: 7, border: "1px solid #ccd5e0", background: "#fff", borderRadius: 8, padding: "0 10px", color: "var(--muted)", fontSize: 12, whiteSpace: "nowrap" }}>
            <span>Mostra</span>
            <select value={pageSize} onChange={(e) => changePageSize(Number(e.target.value))} style={{ border: 0, outline: 0, background: "transparent", color: "#1b2738", fontWeight: 600, cursor: "pointer" }}>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={150}>150</option>
            </select>
          </label>
          {(remote?.total ?? 0) > pageSize && <div className="pagination header-pagination" aria-label="Paginazione fatture">
            <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, remote.total)} di {remote.total}</span>
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>← Precedenti</button>
            <button disabled={(page + 1) * pageSize >= remote.total} onClick={() => setPage(page + 1)}>Successivi →</button>
          </div>}
        </div>
        </div>
      </PageHeader>
      {q.trim() ? (
        <>
          <section className="panel list-panel">
            <div className="panel-title">
              <h2>
                <Search size={18} /> Ricerca locale
              </h2>
              {live?.summary && (
                <Status tone="ok">
                  {live.summary.rows} righe · {euro(live.summary.row_total)}
                </Status>
              )}
            </div>
            {!live ? (
              <Loading />
            ) : live.results?.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th><SortHeader label="Descrizione" sort={sort} sortKey="descrizione" onSort={toggleSort} /></th>
                      <th><SortHeader label="Data" sort={sort} sortKey="data" onSort={toggleSort} /></th>
                      <th><SortHeader label="Fornitore" sort={sort} sortKey="fornitore" onSort={toggleSort} /></th>
                      <th><SortHeader label="Fattura" sort={sort} sortKey="numero" onSort={toggleSort} /></th>
                      <th>Quantità</th>
                      <th><SortHeader label="Prezzo unit." sort={sort} sortKey="prezzo" onSort={toggleSort} /></th>
                      <th><SortHeader label="Totale riga" sort={sort} sortKey="totale" onSort={toggleSort} /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedLiveItems.map((r: any) => (
                      <tr key={r.row_id}>
                        <td>
                          <b>{r.description}</b>
                        </td>
                        <td>{shortDate(r.date)}</td>
                        <td>{r.supplier}</td>
                        <td>{r.invoice}</td>
                        <td>
                          {r.quantity} {r.unit || ""}
                        </td>
                        <td>{euro(r.unit_price)}</td>
                        <td>
                          <b>{euro(r.row_total)}</b>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Nessun risultato locale"
                text="La ricerca locale prova FTS5 e, se serve, RapidFuzz."
              />
            )}
          </section>
          <section className="panel list-panel">
            <div className="panel-title">
              <h2>Risultati Supabase</h2>
              {remote?.count != null && (
                <Status tone="ok">{remote.count} righe</Status>
              )}
            </div>
            {remote?.items?.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th><SortHeader label="Descrizione" sort={sort} sortKey="descrizione" onSort={toggleSort} /></th>
                      <th><SortHeader label="Data" sort={sort} sortKey="data" onSort={toggleSort} /></th>
                      <th><SortHeader label="Fornitore" sort={sort} sortKey="fornitore" onSort={toggleSort} /></th>
                      <th><SortHeader label="Fattura" sort={sort} sortKey="numero" onSort={toggleSort} /></th>
                      <th>Quantità</th>
                      <th><SortHeader label="Prezzo" sort={sort} sortKey="prezzo" onSort={toggleSort} /></th>
                      <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRemoteItems.map((r: any, i: number) => (
                      <tr key={`${r.id}-${r.original_description}-${i}`} onClick={() => openDetail(r.source_hash || r.id)} style={{ cursor: "pointer" }}>
                        <td>
                          <b>{r.original_description}</b>
                        </td>
                        <td>{shortDate(r.invoice_date)}</td>
                        <td>{r.supplier_name}</td>
                        <td>{r.invoice_number}</td>
                        <td>{r.quantity}</td>
                        <td>{euro(Number(r.unit_price))}</td>
                        <td>
                          <b>{euro(Number(r.line_total))}</b>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Archivio centrale non disponibile"
                text={
                  remote?.message ||
                  "Configura la sessione Supabase per visualizzare i dati remoti."
                }
              />
            )}
          </section>
          {detail && (
            <article className="panel detail-panel detail-preview-panel">
              {detail.error ? <Empty title="Dettaglio non disponibile" text={detail.error} /> : <>
                <div className="panel-title"><h2>Anteprima · Fattura {detail.invoice_number || ""}</h2><button className="secondary-btn preview-close" aria-label="Chiudi anteprima" title="Chiudi anteprima" onClick={() => setDetail(undefined)}>×</button></div>
                <p><b>Fornitore:</b> {detail.supplier_name || "—"} · <b>Data:</b> {detail.invoice_date || "—"} · <b>Totale:</b> {euro(Number(detail.total))}</p>
                {detail.rows?.length ? <div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Quantità</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th><th>Totale riga</th></tr></thead><tbody>{detail.rows.map((row: any, i: number) => { const normalized = row.normalized_price != null ? Number(row.normalized_price) : Number(row.quantity) > 0 && row.line_total != null ? Number(row.line_total) / Number(row.quantity) : null; const unit = row.normalized_unit || row.original_unit || "unità"; return <tr key={`${row.original_description}-${i}`}><td>{row.original_description || row.normalized_description || "—"}</td><td>{row.quantity ?? "—"} {row.original_unit || row.normalized_unit || ""}</td><td>{row.unit_price != null ? euro(Number(row.unit_price)) : "—"}</td><td>{normalized != null && Number.isFinite(normalized) ? `${euro(normalized)} / ${unit}` : "Non disponibile"}</td><td>{row.line_total != null ? euro(Number(row.line_total)) : "—"}</td></tr>})}</tbody></table></div> : <p>Nessuna riga prodotto disponibile.</p>}
              </>}
            </article>
          )}
        </>
      ) : (
        <>
          {(!items || items.length > 0 || !remote?.items?.length) && <section className="panel list-panel">
            {!items ? (
              <Loading />
            ) : items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th><SortHeader label="Numero" sort={sort} sortKey="numero" onSort={toggleSort} /></th>
                      <th><SortHeader label="Data" sort={sort} sortKey="data" onSort={toggleSort} /></th>
                      <th><SortHeader label="Fornitore" sort={sort} sortKey="fornitore" onSort={toggleSort} /></th>
                      <th>Prodotti</th>
                      <th><SortHeader label="Imponibile" sort={sort} sortKey="imponibile" onSort={toggleSort} /></th>
                      <th><SortHeader label="IVA" sort={sort} sortKey="iva" onSort={toggleSort} /></th>
                      <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th>
                      <th>Stato</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedLocalItems.map((i) => (
                      <tr key={i.id}>
                        <td>
                          <b>{i.numero}</b>
                        </td>
                        <td>{shortDate(i.data)}</td>
                        <td>{i.supplier.ragione_sociale}</td>
                        <td>{i.row_count}</td>
                        <td>{euro(i.imponibile)}</td>
                        <td>{euro(i.iva)}</td>
                        <td>
                          <b>{euro(i.totale)}</b>
                        </td>
                        <td>
                          <Status>{i.stato_importazione}</Status>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty />
            )}
          </section>}
          <section className="panel list-panel">
            <div className="panel-title">
              <h2>Archivio centrale Supabase</h2>
              {remote?.count != null && (
                <Status tone="ok">
                  {remote.total ?? remote.count} fatture totali · pagina {page + 1}
                </Status>
              )}
            </div>
            {remote?.items?.length ? (
              <div className="table-wrap">
                {centralHasRows ? (
                  <table>
                    <thead>
                      <tr>
                        <th><SortHeader label="Descrizione" sort={sort} sortKey="descrizione" onSort={toggleSort} /></th>
                        <th><SortHeader label="Data" sort={sort} sortKey="data" onSort={toggleSort} /></th>
                        <th><SortHeader label="Fornitore" sort={sort} sortKey="fornitore" onSort={toggleSort} /></th>
                        <th><SortHeader label="Fattura" sort={sort} sortKey="numero" onSort={toggleSort} /></th>
                        <th>Quantità</th>
                        <th><SortHeader label="Prezzo" sort={sort} sortKey="prezzo" onSort={toggleSort} /></th>
                        <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRemoteItems.map((r: any, i: number) => (
                        <tr key={`${r.id}-${r.original_description}-${i}`} onClick={() => openDetail(r.source_hash || r.id)} style={{ cursor: "pointer" }}>
                          <td>
                            <b>{r.original_description}</b>
                          </td>
                          <td>{shortDate(r.invoice_date)}</td>
                          <td>{r.supplier_name}</td>
                          <td>{r.invoice_number}</td>
                          <td>{r.quantity}</td>
                          <td>{euro(Number(r.unit_price))}</td>
                          <td>
                            <b>{euro(Number(r.line_total))}</b>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th><SortHeader label="Numero" sort={sort} sortKey="numero" onSort={toggleSort} /></th>
                        <th><SortHeader label="Data" sort={sort} sortKey="data" onSort={toggleSort} /></th>
                        <th><SortHeader label="Fornitore" sort={sort} sortKey="fornitore" onSort={toggleSort} /></th>
                        <th><SortHeader label="Imponibile" sort={sort} sortKey="imponibile" onSort={toggleSort} /></th>
                        <th><SortHeader label="IVA" sort={sort} sortKey="iva" onSort={toggleSort} /></th>
                        <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th>
                      </tr>
                    </thead>
                    <tbody>
                        {sortedRemoteItems.map((r: any) => (
                        <tr key={r.id} onClick={() => openDetail(r.source_hash || r.id)} style={{ cursor: "pointer" }}>
                          <td>
                            <b>{r.invoice_number}</b>
                          </td>
                          <td>{shortDate(r.invoice_date)}</td>
                          <td>{r.supplier_name}</td>
                          <td>{euro(Number(r.taxable))}</td>
                          <td>{euro(Number(r.vat))}</td>
                          <td>
                            <b>{euro(Number(r.total))}</b>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {detail && (
                  <article className="panel detail-panel detail-preview-panel">
                    {detail.error ? <Empty title="Dettaglio non disponibile" text={detail.error} /> : <>
                      <div className="panel-title"><h2>Anteprima · Fattura {detail.invoice_number || ""}</h2><button className="secondary-btn preview-close" aria-label="Chiudi anteprima" title="Chiudi anteprima" onClick={() => setDetail(undefined)}>×</button></div>
                      <p><b>Fornitore:</b> {detail.supplier_name || "—"} · <b>Data:</b> {detail.invoice_date || "—"} · <b>Totale:</b> {euro(Number(detail.total))}</p>
                      {detail.rows?.length ? <div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Quantità</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th><th>Totale riga</th></tr></thead><tbody>{detail.rows.map((row: any, i: number) => { const normalized = row.normalized_price != null ? Number(row.normalized_price) : Number(row.quantity) > 0 && row.line_total != null ? Number(row.line_total) / Number(row.quantity) : null; const unit = row.normalized_unit || row.original_unit || "unità"; return <tr key={`${row.original_description}-${i}`}><td>{row.original_description || row.normalized_description || "—"}</td><td>{row.quantity ?? "—"} {row.original_unit || row.normalized_unit || ""}</td><td>{row.unit_price != null ? euro(Number(row.unit_price)) : "—"}</td><td>{normalized != null && Number.isFinite(normalized) ? `${euro(normalized)} / ${unit}` : "Non disponibile"}</td><td>{row.line_total != null ? euro(Number(row.line_total)) : "—"}</td></tr>})}</tbody></table></div> : <p>Nessuna riga prodotto disponibile.</p>}
                    </>}
                  </article>
                )}
              </div>
            ) : (
              <Empty
                title="Archivio centrale non disponibile"
                text={
                  remote?.message ||
                  "Configura la sessione Supabase per visualizzare i dati remoti."
                }
              />
            )}
          </section>
        </>
      )}
    </>
  );
}

export function Products() {
  const [items, setItems] = useState<any[]>(),
    [configs, setConfigs] = useState<Record<string, any>>({}),
    [tracking, setTracking] = useState<Record<string, boolean>>({}),
    [q, setQ] = useState(""),
    [pageSize, setPageSize] = useState(50),
    [page, setPage] = useState(0),
    [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "nome_canonico", direction: "asc"}),
    [detail, setDetail] = useState<any>(),
    [configuredName, setConfiguredName] = useState(""),
    [manufacturer, setManufacturer] = useState(""),
    [configSaved, setConfigSaved] = useState(false),
    [tracked, setTracked] = useState(false);
  const productsRequest = useRef(0);
  useEffect(() => {
    api<Record<string, any>>("/product-config").then(setConfigs).catch(() => setConfigs({}));
    api<Record<string, boolean>>("/product-tracking").then(setTracking).catch(() => setTracking({}));
  }, []);
  useEffect(() => {
    setPage(0);
    const requestId = ++productsRequest.current;
    setItems(undefined);
    api<any[]>(`/products?q=${encodeURIComponent(q)}&limit=200`).then((result) => {
      if (requestId === productsRequest.current) setItems(result);
    }).catch(() => {
      if (requestId === productsRequest.current) setItems([]);
    });
  }, [q]);
  const totalItems = items?.length || 0;
  const toggleSort = (key: SortKey) => setSort((current) => current.key === key ? {key, direction: current.direction === "asc" ? "desc" : "asc"} : {key, direction: "asc"});
  const sortedItems = useMemo(() => [...(items || [])].sort((a, b) => compareValues(a[sort.key], b[sort.key], sort.direction)), [items, sort]);
  const visibleItems = sortedItems.slice(page * pageSize, (page + 1) * pageSize);
  async function openDetail(name: string, aliases: string[] = [name]) {
    try {
      const details = (await Promise.all(aliases.map((alias) => eyeApi<any>(`/central/products/${encodeURIComponent(alias)}`).catch(() => null)))).filter(Boolean);
      if (!details.length) throw new Error("Dettaglio prodotto non disponibile");
      const products = details.map((item) => item.product).filter(Boolean);
      const history = details.flatMap((item) => item.history || []);
      const purchases = products.reduce((sum, item) => sum + Number(item.purchases || 0), 0);
      const weighted = products.reduce((sum, item) => sum + Number(item.avg_price || 0) * Number(item.purchases || 0), 0);
      const product = { ...products[0], canonical_name: name, purchases, avg_price: purchases ? weighted / purchases : products[0].avg_price, min_price: Math.min(...products.map((item) => Number(item.min_price ?? Infinity))), max_price: Math.max(...products.map((item) => Number(item.max_price ?? -Infinity))) };
      setDetail({ ...details[0], product, history, sourceName: name, sourceNames: aliases });
      setConfiguredName(configs[name]?.configured_name || name);
      setManufacturer(configs[name]?.manufacturer || product.brand || product.marca || "");
      setTracked(Boolean(tracking[name]));
      setConfigSaved(false);
    } catch {
      setDetail({ error: "Dettaglio prodotto non disponibile" });
    }
  }
  async function saveProductConfig() {
    if (!detail?.sourceName || !configuredName.trim()) return;
    const saved = await api<any>("/product-config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_name: detail.sourceName, configured_name: configuredName.trim(), manufacturer: manufacturer.trim() }) });
    setConfigs(current => ({ ...current, [detail.sourceName]: saved })); setConfigSaved(true);
  }
  async function saveTracking(enabled: boolean) {
    if (!detail?.sourceName) return;
    await api("/product-tracking", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_name: detail.sourceName, enabled }) });
    setTracked(enabled);
    setTracking(current => enabled ? ({ ...current, [detail.sourceName]: true }) : Object.fromEntries(Object.entries(current).filter(([key]) => key !== detail.sourceName)));
  }
  return (
    <>
      <PageHeader
        title="Prodotti"
        subtitle="Prodotti canonici, prezzi e storico"
      >
        <div className="list-header-controls"><div className="list-header-main">
          <SearchBox value={q} onChange={setQ} placeholder="Nome, marca o codice…" />
          <label className="page-size-control"><span>Mostra</span><select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0); }}><option value={50}>50</option><option value={100}>100</option><option value={150}>150</option></select></label>
        </div><div className="pagination header-pagination" aria-label="Paginazione prodotti"><span>{totalItems ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, totalItems)} di ${totalItems}` : "Nessun prodotto"}</span><button disabled={page === 0} onClick={() => setPage((value) => value - 1)}>← Precedenti</button><button disabled={(page + 1) * pageSize >= totalItems} onClick={() => setPage((value) => value + 1)}>Successivi →</button></div></div>
      </PageHeader>
      <section className="panel list-panel">
        {!items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                    <tr>
                      <th><SortHeader label="Nome canonico" sort={sort} sortKey="nome_canonico" onSort={toggleSort} /></th>
                  <th>Categoria</th>
                  <th>Marca</th>
                      <th><SortHeader label="Acquisti" sort={sort} sortKey="purchases" onSort={toggleSort} /></th>
                      <th><SortHeader label="Minimo" sort={sort} sortKey="min_price" onSort={toggleSort} /></th>
                      <th><SortHeader label="Media" sort={sort} sortKey="avg_price" onSort={toggleSort} /></th>
                      <th><SortHeader label="Massimo" sort={sort} sortKey="max_price" onSort={toggleSort} /></th>
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((p) => (
                  <tr key={p.id} onClick={() => openDetail(p.nome_canonico, p.canonical_names || [p.nome_canonico])} style={{ cursor: "pointer" }}>
                    <td>
                      <b>{configs[p.nome_canonico]?.configured_name || p.nome_canonico}</b>
                    </td>
                    <td>{p.categoria || "—"}</td>
                    <td>{configs[p.nome_canonico]?.manufacturer || p.marca || "—"}</td>
                    <td>{p.purchases}</td>
                    <td>{p.min_price ? euro(p.min_price) : "—"}</td>
                    <td>{p.avg_price ? euro(p.avg_price) : "—"}</td>
                    <td>{p.max_price ? euro(p.max_price) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Nessun prodotto canonico"
            text="I prodotti possono essere creati e collegati alle righe fattura."
          />
        )}
      </section>
      {detail && (
        <article className="panel detail-panel detail-preview-panel">
          {detail.error ? <Empty title="Dettaglio prodotto non disponibile" text={detail.error} /> : <>
            <div className="panel-title"><h2>Anteprima · {detail.product?.canonical_name || "Dettaglio prodotto"}</h2><button className="secondary-btn preview-close" aria-label="Chiudi anteprima" title="Chiudi anteprima" onClick={() => setDetail(undefined)}>×</button></div>
            <div className="product-config"><h3>Configurazione prodotto</h3><div className="product-config-grid"><label>Nome visualizzato<input value={configuredName} onChange={e => setConfiguredName(e.target.value)} /></label><label>Produttore<input value={manufacturer} onChange={e => setManufacturer(e.target.value)} placeholder="Produttore / marca" /></label></div><button className="primary-btn" onClick={saveProductConfig} disabled={!configuredName.trim()}>Salva configurazione</button>{configSaved && <span className="success">Configurazione salvata</span>}<label className="product-track-toggle"><input type="checkbox" checked={tracked} onChange={e => saveTracking(e.target.checked)} /> Monitora questo prodotto e segnala variazioni di prezzo</label></div>
            <p><b>Acquisti:</b> {detail.product?.purchases ?? 0} · <b>Prezzo medio:</b> {detail.product?.avg_price != null ? euro(Number(detail.product.avg_price)) : "—"}</p>
            {detail.history?.length ? <div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Fornitore</th><th>Quantità</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th><th>Totale</th></tr></thead><tbody>{detail.history.map((h: any, i: number) => <tr key={`${h.source_hash}-${i}`}><td>{shortDate(h.invoice_date)}</td><td>{h.invoice_number}</td><td>{h.supplier_name}</td><td>{h.quantity ?? "—"} {h.original_unit || h.normalized_unit || ""}</td><td>{h.unit_price != null ? euro(Number(h.unit_price)) : "—"}</td><td>{h.normalized_price != null ? `${euro(Number(h.normalized_price))} / ${h.normalized_unit || h.original_unit || "unità"}` : "—"}</td><td>{h.line_total != null ? euro(Number(h.line_total)) : "—"}</td></tr>)}</tbody></table></div> : <p>Nessun acquisto collegato.</p>}
          </>}
        </article>
      )}
    </>
  );
}
export function Suppliers() {
  type SupplierSortKey = "ragione_sociale" | "partita_iva" | "codice_fiscale" | "invoice_count" | "total_spent" | "last_invoice_date";
  const [items, setItems] = useState<any[]>(),
    [q, setQ] = useState(""),
    [detail, setDetail] = useState<any>(),
    [invoiceDetail, setInvoiceDetail] = useState<any>(),
    [selectedSupplierId, setSelectedSupplierId] = useState<string>(),
    [pageSize, setPageSize] = useState(50),
    [page, setPage] = useState(0),
    [sort, setSort] = useState<{ key: SupplierSortKey; direction: "asc" | "desc" }>({ key: "ragione_sociale", direction: "asc" });
  useEffect(() => {
    setItems(undefined);
    setDetail(undefined);
    setInvoiceDetail(undefined);
    setSelectedSupplierId(undefined);
    setPage(0);
    eyeApi<any>(`/central/suppliers?q=${encodeURIComponent(q)}&limit=2000`).then((data) => setItems(data.items || [])).catch(() =>
      api<any[]>(`/suppliers?q=${encodeURIComponent(q)}`).then(setItems),
    );
  }, [q]);
  const toggleSort = (key: SupplierSortKey) => setSort((current) => current.key === key ? { key, direction: current.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" });
  const sortIndicator = (key: SupplierSortKey) => sort.key === key ? (sort.direction === "asc" ? " ↑" : " ↓") : "";
  const sortedItems = [...(items || [])].sort((a, b) => {
    const left = a[sort.key], right = b[sort.key];
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    const numeric = ["invoice_count", "total_spent"].includes(sort.key);
    const result = numeric ? Number(left) - Number(right) : String(left).localeCompare(String(right), "it", { numeric: true, sensitivity: "base" });
    return (sort.direction === "asc" ? 1 : -1) * result;
  });
  const visibleItems = sortedItems.slice(page * pageSize, (page + 1) * pageSize);
  const totalItems = items?.length || 0;
  const openDetail = (id: string) => { setSelectedSupplierId(id); setDetail(undefined); setInvoiceDetail(undefined); eyeApi<any>(`/central/suppliers/${encodeURIComponent(id)}`).then(setDetail).catch((error: any) => setDetail({ error: error.message })); };
  const openInvoiceDetail = (sourceHash: string) => eyeApi<any>(`/central/invoices/${encodeURIComponent(sourceHash)}`).then(setInvoiceDetail).catch((error: any) => setInvoiceDetail({ error: error.message }));
  return (
    <>
      <PageHeader
        title="Fornitori"
        subtitle="Anagrafiche e storico commerciale"
      >
        <div className="list-header-controls"><div className="list-header-main">
          <SearchBox
            value={q}
            onChange={setQ}
            placeholder="Ragione sociale o P. IVA…"
          />
          <label className="page-size-control" style={{ height: 42, display: "flex", alignItems: "center", gap: 7, border: "1px solid #ccd5e0", background: "#fff", borderRadius: 8, padding: "0 10px", color: "var(--muted)", fontSize: 12, whiteSpace: "nowrap" }}>
            <span>Mostra</span>
            <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0); }} style={{ border: 0, outline: 0, background: "transparent", color: "#1b2738", fontWeight: 600, cursor: "pointer" }}>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={150}>150</option>
            </select>
          </label>
          </div><div className="pagination header-pagination" aria-label="Paginazione fornitori">
            <span>{totalItems ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, totalItems)} di ${totalItems}` : "Nessun fornitore"}</span>
            <button disabled={page === 0} onClick={() => setPage((value) => value - 1)}>← Precedenti</button>
            <button disabled={(page + 1) * pageSize >= totalItems} onClick={() => setPage((value) => value + 1)}>Successivi →</button>
          </div></div>
      </PageHeader>
      <section className="panel list-panel">
        {!items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {([['ragione_sociale', 'Ragione sociale'], ['partita_iva', 'Partita IVA'], ['codice_fiscale', 'Codice fiscale'], ['invoice_count', 'Fatture'], ['total_spent', 'Spesa fatture'], ['last_invoice_date', 'Ultima fattura']] as [SupplierSortKey, string][]).map(([key, label]) => <th key={key}><button type="button" onClick={() => toggleSort(key)} style={{ border: 0, background: "transparent", padding: 0, font: "inherit", color: "inherit", fontWeight: 700, cursor: "pointer" }}>{label}{sortIndicator(key)}</button></th>)}
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((s) => (
                  <Fragment key={s.id}>
                    <tr onClick={() => openDetail(s.id)} style={{ cursor: "pointer" }} title="Apri dettaglio fornitore">
                      <td><b>{s.ragione_sociale}</b></td>
                      <td>{s.partita_iva || "—"}</td>
                      <td>{s.codice_fiscale || "—"}</td>
                      <td>{s.invoice_count ?? "—"}</td>
                      <td>{s.total_spent != null ? euro(Number(s.total_spent)) : "—"}</td>
                      <td>{s.last_invoice_date ? shortDate(s.last_invoice_date) : "—"}</td>
                    </tr>
                    {selectedSupplierId === s.id && detail && <tr>
                      <td colSpan={6}>
                        <article className="detail-panel detail-preview-panel">
                          {detail.error ? <Empty title="Dettaglio fornitore non disponibile" text={detail.error} /> : <>
                          <div className="panel-title"><h2>Anteprima · {detail.supplier?.ragione_sociale || "Dettaglio fornitore"}</h2><button className="secondary-btn preview-close" aria-label="Chiudi anteprima" title="Chiudi anteprima" onClick={() => { setDetail(undefined); setSelectedSupplierId(undefined); }}>×</button></div>
                          <div className="kpi-grid">
                            <div><span>Partita IVA</span><b>{detail.supplier?.partita_iva || "—"}</b></div>
                            <div><span>Codice fiscale</span><b>{detail.supplier?.codice_fiscale || "—"}</b></div>
                            <div><span>Fatture</span><b>{detail.supplier?.invoice_count ?? 0}</b></div>
                            <div><span>Spesa fatture (note escluse)</span><b>{euro(Number(detail.supplier?.total_spent || 0))}</b></div>
                            <div><span>Note di accredito</span><b>{euro(Number(detail.supplier?.credit_total || 0))}</b></div>
                            <div><span>Carburante rilevato</span><b>{euro(Number(detail.fuel_total || 0))}</b></div>
                          </div>
                          <p><b>Indirizzo:</b> {detail.supplier?.indirizzo || "Non disponibile nei dati centrali"} · <b>Email:</b> {detail.supplier?.email || "Non disponibile"} · <b>Telefono:</b> {detail.supplier?.telefono || "Non disponibile"}</p>
                          <p><b>Sconti:</b> non presenti come campo strutturato nelle fatture importate. Le righe e i totali originali restano consultabili qui sotto.</p>
                          {detail.invoices?.length ? <div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Destinazione</th><th>Imponibile</th><th>Totale</th></tr></thead><tbody>{detail.invoices.map((i: any) => <tr key={i.id} onClick={() => openInvoiceDetail(i.source_hash)} style={{ cursor: "pointer" }} title="Apri dettaglio fattura"><td>{shortDate(i.invoice_date)}</td><td><b>{i.invoice_number}</b></td><td>{i.destination_hotel || "—"}</td><td>{euro(Number(i.taxable || 0))}</td><td>{euro(Number(i.total || 0))}</td></tr>)}</tbody></table></div> : <p>Nessuna fattura collegata.</p>}
                          {invoiceDetail && <article className="panel detail-panel detail-preview-panel">
                            {invoiceDetail.error ? <Empty title="Dettaglio fattura non disponibile" text={invoiceDetail.error} /> : <>
                              <div className="panel-title"><h3>Anteprima · Fattura {invoiceDetail.invoice_number || ""}</h3><button className="secondary-btn preview-close" aria-label="Chiudi fattura" title="Chiudi fattura" onClick={() => setInvoiceDetail(undefined)}>×</button></div>
                              <p><b>Data:</b> {invoiceDetail.invoice_date || "—"} · <b>Fornitore:</b> {invoiceDetail.supplier_name || "—"} · <b>Totale:</b> {euro(Number(invoiceDetail.total || 0))}</p>
                              {invoiceDetail.rows?.length ? <div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Quantità</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th><th>Totale riga</th></tr></thead><tbody>{invoiceDetail.rows.map((row: any, i: number) => { const normalized = row.normalized_price != null ? Number(row.normalized_price) : Number(row.quantity) > 0 && row.line_total != null ? Number(row.line_total) / Number(row.quantity) : null; const unit = row.normalized_unit || row.original_unit || "unità"; return <tr key={`${row.original_description}-${i}`}><td>{row.original_description || row.normalized_description || "—"}</td><td>{row.quantity ?? "—"} {row.original_unit || row.normalized_unit || ""}</td><td>{row.unit_price != null ? euro(Number(row.unit_price)) : "—"}</td><td>{normalized != null && Number.isFinite(normalized) ? `${euro(normalized)} / ${unit}` : "Non disponibile"}</td><td>{row.line_total != null ? euro(Number(row.line_total)) : "—"}</td></tr>})}</tbody></table></div> : <p>Nessuna riga prodotto disponibile.</p>}
                            </>}
                          </article>}
                          {detail.categories?.length ? <><h3>Principali voci acquistate</h3><div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Riferimento fattura</th><th>Acquisti</th><th>Totale</th></tr></thead><tbody>{detail.categories.map((c: any, i: number) => <tr key={`${c.description}-${i}`}><td>{c.description}</td><td>{c.invoice_references || "—"}</td><td>{c.purchases}</td><td>{euro(Number(c.total || 0))}</td></tr>)}</tbody></table></div></> : null}
                          </>}
                        </article>
                      </td>
                    </tr>}
                  </Fragment>
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
export function Reports({ go }: { go: (p: Page) => void }) {
  return (
    <>
      <PageHeader
        title="Report"
        subtitle="Analisi deterministiche ed esportazioni"
      >
        <a className="primary-btn" href="/api/reports/spending.csv">
          <Download size={17} />
          Esporta CSV
        </a>
      </PageHeader>
      <section className="report-grid">
        {[
          "Spesa per mese",
          "Spesa per anno",
          "Spesa per fornitore",
          "Spesa per categoria",
          "Prodotti più acquistati",
          "Aumento prezzi",
          "Confronto fornitori",
          "Duplicati e anomalie",
        ].map((x) => (
          <button
            className="panel report"
            key={x}
            onClick={() =>
              go(
                x.includes("fornitore")
                  ? "suppliers"
                  : x.includes("Prodotti")
                    ? "products"
                    : x.includes("storico")
                      ? "history"
                      : x.includes("Aumento") || x.includes("Duplicati")
                        ? "anomalies"
                        : x.includes("categoria")
                          ? "categories"
                          : "history",
              )
            }
          >
            <div>
              <b>{x}</b>
              <span>Apri sezione analisi</span>
            </div>
            <ChevronRight />
          </button>
        ))}
      </section>
    </>
  );
}
export function HistoryPage() {
  return (
    <>
      <PageHeader
        title="Storico prezzi"
        subtitle="Cerca un prodotto e confronta l’andamento nel tempo per fornitore"
      />
      <section className="panel list-panel history-product-section">
        <HistoricalReportPage embedded />
      </section>
    </>
  );
}

export function AlertsPage() {
  const [items, setItems] = useState<any[]>(),
    [unreadOnly, setUnreadOnly] = useState(false),
    [tracking, setTracking] = useState<Record<string, boolean>>({}),
    [refreshing, setRefreshing] = useState(false),
    [error, setError] = useState(""),
    [permission, setPermission] = useState(
      typeof Notification !== "undefined" ? Notification.permission : "denied",
    );
  async function load() {
    try { setError(""); setItems(await eyeApi<any[]>(`/alerts?unread_only=${unreadOnly}&limit=500`)); }
    catch (e: any) { setError(e.message || "Impossibile caricare gli alert"); }
  }
  useEffect(() => {
    load();
    api<Record<string, boolean>>("/product-tracking").then(setTracking).catch(() => setTracking({}));
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [unreadOnly]);
  async function refresh() { setRefreshing(true); await load(); setRefreshing(false); }
  async function markRead(id: number | string) {
    if (typeof id !== "number") return;
    try { await eyeApi(`/alerts/${id}/read`, { method: "POST" }); await load(); } catch (e: any) { setError(e.message || "Impossibile aggiornare l'alert"); }
  }
  async function enable() {
    if (typeof Notification === "undefined") return;
    const p = await Notification.requestPermission();
    setPermission(p);
    if (p === "granted")
      new Notification("Eye Supremo", { body: "Notifiche Windows attivate." });
  }
  useEffect(() => {
    if (permission === "granted" && items?.length) {
      const unread = items.find((x) => !x.is_read && !x.resolved);
      if (unread) {
        const key = `eye-alert-${unread.id}`;
        if (!sessionStorage.getItem(key)) {
          new Notification(unread.title, { body: unread.description });
          sessionStorage.setItem(key, "1");
        }
      }
    }
  }, [items, permission]);
  return (
    <>
      <PageHeader
        title="Alert e notifiche"
        subtitle="Aumenti prezzo, anomalie e righe da attenzionare"
      >
        <div className="alert-header-actions"><button className="secondary-btn" onClick={refresh} disabled={refreshing}>{refreshing ? "Aggiorno…" : "Aggiorna"}</button><button className="primary-btn" onClick={enable}><Bell size={17} />{permission === "granted" ? "Notifiche attive" : "Attiva notifiche"}</button></div>
      </PageHeader>
      <section className="panel list-panel">
        <div className="tracked-products"><div><h3>Prezzi monitorati</h3><p>Prodotti selezionati per controllare gli aggiornamenti di prezzo.</p></div><b>{Object.keys(tracking).length}</b></div>
        {Object.keys(tracking).length > 0 && <div className="tracked-product-list">{Object.keys(tracking).map(name => <span key={name}>{name}</span>)}</div>}
        <div className="alerts-toolbar"><div><b>{items?.length ?? 0}</b> alert caricati <span className="alert-unread">{items?.filter(a => !a.is_read && !a.resolved).length ?? 0} non letti</span></div><div className="review-filters"><button className={!unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(false)}>Tutti</button><button className={unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(true)}>Non letti</button></div></div>
        {error ? <div className="error alerts-error">{error}</div> : !items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Gravità</th>
                  <th>Tipo</th>
                  <th>Alert</th>
                  <th>Descrizione</th>
                  <th>Data</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className={!a.is_read && !a.resolved ? "alert-unread-row" : ""}>
                    <td>
                      <Status
                        tone={
                          a.severity === "high"
                            ? "danger"
                            : a.severity === "warning"
                              ? "warn"
                              : "ok"
                        }
                      >
                        {a.severity}
                      </Status>
                    </td>
                    <td>{a.kind}</td>
                    <td>
                      <b>{a.title}</b>
                    </td>
                    <td>{a.description}</td>
                    <td>{new Date(a.created_at).toLocaleString("it-IT")}</td>
                    <td>{!a.is_read && !a.resolved && typeof a.id === "number" && <button className="alert-read-btn" onClick={() => markRead(a.id)}>Segna letto</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Nessun alert"
            text="Eye Supremo controllerà prezzi e anomalie durante le importazioni."
          />
        )}
      </section>
    </>
  );
}

const PRODUCT_CATEGORY_OPTIONS: Record<string, string[]> = {
  "Food & Beverage": ["Colazioni", "Bevande", "Cucina", "Dispensa"],
  "Pulizia e igiene": ["Detergenti", "Carta", "Amenities"],
  "Camere e housekeeping": ["Biancheria", "Asciugamani", "Accessori camera"],
  Manutenzione: ["Elettrico", "Idraulica", "Climatizzazione", "Ferramenta"],
  "Arredi e attrezzature": ["Arredi", "Attrezzature cucina", "Attrezzature hotel"],
  "Ufficio e informatica": ["Cancelleria", "Hardware", "Software"],
  Altro: ["Generico"],
  "Da classificare": [],
};

const EXPENSE_CATEGORIES = [
  ["Utenze", "Acqua, luce, gas e telecomunicazioni"],
  ["Trasporti e consegne", "Consegne, corrieri e trasporto merci"],
  ["Carburante", "Benzina, gasolio e rifornimenti"],
  ["Manodopera", "Interventi e prestazioni operative"],
  ["Consulenze", "Servizi professionali e consulenze"],
  ["Canoni e abbonamenti", "Canoni ricorrenti e licenze"],
  ["Commissioni e spese bancarie", "Commissioni, bolli e spese finanziarie"],
  ["Tasse e diritti", "Imposte, diritti e altri oneri"],
] as const;

function suggestedProductCategory(name: string) {
  const value = name.toLowerCase();
  if (/acqua|bevanda|vino|birra|caffe|caff[eè]|pasta|farina|olio|zuccher|colazion/.test(value)) return "Food & Beverage";
  if (/deterg|igien|carta|sapone|shampoo|amenit|disinfett/.test(value)) return "Pulizia e igiene";
  if (/lenzuol|asciugaman|copriletto|cuscino|camera|appendiabiti/.test(value)) return "Camere e housekeeping";
  if (/lampad|elettric|presa|rubinett|tubo|filtro|climat|vernice|vite|bullon/.test(value)) return "Manutenzione";
  if (/sedia|tavol|frigor|forno|attrezz|carrello/.test(value)) return "Arredi e attrezzature";
  if (/carta a4|penna|toner|stampant|computer|mouse|tastier|software/.test(value)) return "Ufficio e informatica";
  return "Da classificare";
}

export function CategoriesPage() {
  const [products, setProducts] = useState<any[]>();
  const [configs, setConfigs] = useState<Record<string, any>>({});
  const [drafts, setDrafts] = useState<Record<string, {category: string; subcategory: string}>>({});
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<any[]>("/products?q=&limit=200"),
      api<Record<string, any>>("/product-config"),
    ]).then(([items, stored]) => {
      setProducts(items);
      setConfigs(stored);
      const initial: Record<string, {category: string; subcategory: string}> = {};
      items.forEach((item) => {
        const name = item.nome_canonico || item.canonical_name;
        const config = stored[name] || {};
        initial[name] = {
          category: config.category || item.categoria || suggestedProductCategory(name),
          subcategory: config.subcategory || item.sottocategoria || "",
        };
      });
      setDrafts(initial);
    }).catch(() => setProducts([]));
  }, []);

  const visible = (products || []).filter((item) => {
    const name = item.nome_canonico || item.canonical_name || "";
    const category = drafts[name]?.category || "Da classificare";
    return name.toLowerCase().includes(q.toLowerCase()) && (filter === "all" || category === filter);
  });

  async function saveCategory(name: string) {
    const draft = drafts[name] || {category: "Da classificare", subcategory: ""};
    const config = configs[name] || {};
    setSaving(name);
    try {
      const result = await api<any>("/product-config", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          source_name: name,
          configured_name: config.configured_name || name,
          manufacturer: config.manufacturer || "",
          category: draft.category,
          subcategory: draft.subcategory,
        }),
      });
      setConfigs((current) => ({...current, [name]: result}));
      setSaved(name);
      window.setTimeout(() => setSaved((current) => current === name ? null : current), 1800);
    } finally {
      setSaving(null);
    }
  }

  return <>
    <PageHeader title="Categorie" subtitle="Classifica prodotti e spese senza confondere beni, servizi e logistica">
      <div className="list-header-main category-toolbar">
        <SearchBox value={q} onChange={setQ} placeholder="Cerca prodotto…" />
        <select className="review-control" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">Tutte le categorie</option>
          {Object.keys(PRODUCT_CATEGORY_OPTIONS).map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
      </div>
    </PageHeader>
    <section className="panel list-panel">
      <div className="panel-title category-panel-title"><div><h2>Prodotti</h2><span>La categoria suggerita può essere corretta e salvata</span></div><Status tone="ok">{visible.length} prodotti</Status></div>
      {!products ? <Loading /> : visible.length ? <div className="table-wrap"><table><thead><tr><th>Prodotto</th><th>Categoria</th><th>Sottocategoria</th><th></th></tr></thead><tbody>
        {visible.map((item) => {
          const name = item.nome_canonico || item.canonical_name;
          const draft = drafts[name] || {category: "Da classificare", subcategory: ""};
          return <tr key={name}><td><b>{configs[name]?.configured_name || name}</b>{draft.category === "Da classificare" && <small className="category-hint">Da verificare</small>}</td><td><select className="category-select" value={draft.category} onChange={(event) => setDrafts((current) => ({...current, [name]: {category: event.target.value, subcategory: ""}}))}>{Object.keys(PRODUCT_CATEGORY_OPTIONS).map((category) => <option key={category}>{category}</option>)}</select></td><td><select className="category-select" value={draft.subcategory} disabled={!PRODUCT_CATEGORY_OPTIONS[draft.category]?.length} onChange={(event) => setDrafts((current) => ({...current, [name]: {...draft, subcategory: event.target.value}}))}><option value="">Nessuna</option>{(PRODUCT_CATEGORY_OPTIONS[draft.category] || []).map((subcategory) => <option key={subcategory}>{subcategory}</option>)}</select></td><td><button className="secondary-btn category-save" disabled={saving === name} onClick={() => saveCategory(name)}>{saving === name ? "Salvo…" : saved === name ? "Salvato" : "Salva"}</button></td></tr>;
        })}
      </tbody></table></div> : <Empty title="Nessun prodotto" text="Importa una fattura XML o cambia il filtro per vedere i prodotti." />}
    </section>
    <section className="panel expense-category-panel"><div className="panel-title"><div><h2>Spese e servizi</h2><span>Restano fuori dal catalogo prodotti ma sono ricercabili nelle fatture e nei fornitori</span></div></div><div className="expense-category-grid">{EXPENSE_CATEGORIES.map(([name, description]) => <article key={name}><b>{name}</b><span>{description}</span></article>)}</div></section>
  </>;
}

export function SimplePage({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <section className="panel list-panel">
        <Empty
          title={`${title} pronto`}
          text="La struttura è disponibile e si popolerà con i dati dell'archivio."
        />
      </section>
    </>
  );
}
