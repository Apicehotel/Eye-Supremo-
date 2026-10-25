import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, ChevronRight, Bell, Search } from "lucide-react";
import { api, eyeApi, euro, shortDate } from "../../lib/api";
import { InvoiceViewer, OpenInvoiceButton, type InvoiceRefTarget } from "../../components/InvoiceRef";
import {
  Empty,
  Loading,
  PageHeader,
  SearchBox,
  Status,
} from "../../components/UI";
import { Page } from "../../components/Shell";
import {useLatestRequest} from "../../hooks/useLatestRequest";
import { HistoricalReportPage } from "../HistoricalReport";

import {SortHeader, compareValues, sortIndicator, type SortDirection, type SortKey} from "./TableSort";
import { supabaseOnline } from "../../lib/supabaseDataService";
export function Invoices() {
  const requests = useLatestRequest();
  const detailRequests = useLatestRequest();
  const [items, setItems] = useState<any[]>(),
    [live, setLive] = useState<any>(),
    [remote, setRemote] = useState<any>(),
    [q, setQState] = useState(""),
    [page, setPage] = useState(0),
    [pageSize, setPageSize] = useState(50),
    [detail, setDetail] = useState<any>(),
    [invoiceRef, setInvoiceRef] = useState<InvoiceRefTarget>(),
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
    const request = detailRequests.start();
    try {
      const result = await eyeApi<any>(`/central/invoices/${encodeURIComponent(sourceHash)}`, {signal:request.signal});
      if(request.current())setDetail(result);
    } catch {if(request.current())setDetail({error:"Dettaglio non disponibile"});}
  }
  useEffect(() => {
    const request = requests.start();
    const t = setTimeout(() => {
      const options = {signal: request.signal};
      const offset = page * pageSize;
      const local = q.trim()
        ? eyeApi<any>(`/search/live?q=${encodeURIComponent(q)}&limit=${pageSize}&offset=${offset}`, options)
        : api<any[]>(`/invoices`, options);
      const central = eyeApi<any>(`/central/invoices?q=${encodeURIComponent(q)}&limit=${pageSize}&offset=${offset}`, options);
      void Promise.allSettled([local, central]).then(([localResult, centralResult]) => {
        if (!request.current()) return;
        if (q.trim()) setLive(localResult.status === 'fulfilled' ? localResult.value : undefined);
        else {setLive(undefined); setItems(localResult.status === 'fulfilled' ? localResult.value : []);}
        setRemote(centralResult.status === 'fulfilled' ? centralResult.value : undefined);
      });
    }, 180);
    return () => {clearTimeout(t); requests.cancel();};
  }, [q, page, pageSize, requests]);
  const searchTotal = Math.max(live?.total ?? 0, remote?.total ?? 0);
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
      <InvoiceViewer target={invoiceRef} onClose={() => setInvoiceRef(undefined)} />
      <PageHeader
        title="Fatture"
        subtitle="Ricerca estesa a tutte le fatture dell’archivio — nessun tetto nascosto"
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
          {(q.trim() ? searchTotal : (remote?.total ?? 0)) > pageSize && <div className="pagination header-pagination" aria-label="Paginazione fatture">
            <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, q.trim() ? searchTotal : remote.total)} di {q.trim() ? searchTotal : remote.total}</span>
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>← Precedenti</button>
            <button disabled={(page + 1) * pageSize >= (q.trim() ? searchTotal : remote.total)} onClick={() => setPage(page + 1)}>Successivi →</button>
          </div>}
        </div>
        </div>
      </PageHeader>
      {q.trim() ? (
        <>
          {!supabaseOnline && <section className="panel list-panel">
            <div className="panel-title">
              <h2>
                <Search size={18} /> Ricerca locale (archivio completo, senza limite)
              </h2>
              {live?.summary && (
                <Status tone="ok">
                  {(live.total ?? live.summary.rows)} risultati in archivio · {euro(live.summary.row_total)}
                  {live.supplier_count != null ? ` · ${live.supplier_count} fornitori` : ""}
                </Status>
              )}
            </div>
            {live?.suppliers?.length > 1 && (
              <p className="muted" style={{ margin: "0 0 12px", fontSize: 13 }}>
                Fornitori: {live.suppliers.slice(0, 8).map((s: any) => `${s.supplier} (${s.rows})`).join(" · ")}
                {live.suppliers.length > 8 ? ` · +${live.suppliers.length - 8} altri` : ""}
              </p>
            )}
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
                      <th>Fattura</th>
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
                        <td><OpenInvoiceButton id={r.invoice_id} highlight={q} onOpen={setInvoiceRef} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Nessun risultato locale"
                text="La ricerca interroga tutto l’indice fatture (FTS). Prova un altro nome prodotto o verifica import/cache."
              />
            )}
          </section>}
          <section className="panel list-panel">
            <div className="panel-title">
              <h2>Risultati cache / centrale</h2>
              {remote?.total != null ? (
                <Status tone="ok">
                  {remote.total} risultati
                  {remote.supplier_count != null ? ` · ${remote.supplier_count} fornitori` : ""}
                </Status>
              ) : remote?.count != null ? (
                <Status tone="ok">{remote.count} righe</Status>
              ) : null}
            </div>
            {remote?.suppliers?.length > 1 && (
              <p className="muted" style={{ margin: "0 0 12px", fontSize: 13 }}>
                Fornitori: {remote.suppliers.slice(0, 8).map((s: any) => `${s.supplier} (${s.rows})`).join(" · ")}
                {remote.suppliers.length > 8 ? ` · +${remote.suppliers.length - 8} altri` : ""}
              </p>
            )}
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
                      <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th><th>Fattura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRemoteItems.map((r: any, i: number) => (
                      <tr key={`${r.id}-${r.original_description}-${i}`} onClick={() => openDetail(r.source_hash || r.id)} style={{ cursor: "pointer" }}>
                        <td data-label="Descrizione">
                          <b>{r.original_description}</b>
                        </td>
                        <td data-label="Data">{shortDate(r.invoice_date)}</td>
                        <td data-label="Fornitore">{r.supplier_name}</td>
                        <td data-label="Fattura">{r.invoice_number}</td>
                        <td data-label="Quantità">{r.quantity}</td>
                        <td data-label="Prezzo">{euro(Number(r.unit_price))}</td>
                        <td data-label="Totale">
                          <b>{euro(Number(r.line_total))}</b>
                        </td><td><OpenInvoiceButton id={r.source_hash || r.id} highlight={q} onOpen={setInvoiceRef} /></td>
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
                        <th><SortHeader label="Totale" sort={sort} sortKey="totale" onSort={toggleSort} /></th><th>Fattura</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRemoteItems.map((r: any, i: number) => (
                        <tr key={`${r.id}-${r.original_description}-${i}`} onClick={() => openDetail(r.source_hash || r.id)} style={{ cursor: "pointer" }}>
                          <td data-label="Descrizione">
                            <b>{r.original_description}</b>
                          </td>
                          <td data-label="Data">{shortDate(r.invoice_date)}</td>
                          <td data-label="Fornitore">{r.supplier_name}</td>
                          <td data-label="Fattura">{r.invoice_number}</td>
                          <td data-label="Quantità">{r.quantity}</td>
                          <td data-label="Prezzo">{euro(Number(r.unit_price))}</td>
                          <td data-label="Totale">
                            <b>{euro(Number(r.line_total))}</b>
                          </td><td><OpenInvoiceButton id={r.source_hash || r.id} highlight={q} onOpen={setInvoiceRef} /></td>
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
                          <td data-label="Fattura n.">
                            <b>{r.invoice_number}</b>
                          </td>
                          <td data-label="Data">{shortDate(r.invoice_date)}</td>
                          <td data-label="Fornitore">{r.supplier_name}</td>
                          <td data-label="Imponibile">{euro(Number(r.taxable))}</td>
                          <td data-label="IVA">{euro(Number(r.vat))}</td>
                          <td data-label="Totale">
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
