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
export function Suppliers() {
  const requests = useLatestRequest();
  const detailRequests = useLatestRequest();
  const invoiceRequests = useLatestRequest();
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
    const request = requests.start();
    detailRequests.cancel(); invoiceRequests.cancel();
    setItems(undefined); setDetail(undefined); setInvoiceDetail(undefined);
    setSelectedSupplierId(undefined); setPage(0);
    async function load() {
      try {
        const data = await eyeApi<any>(`/central/suppliers?q=${encodeURIComponent(q)}&limit=2000`, {signal:request.signal});
        if (request.current()) setItems(data.items || []);
      } catch {
        if (!request.current()) return;
        try {
          const local = await api<any[]>(`/suppliers?q=${encodeURIComponent(q)}`, {signal:request.signal});
          if (request.current()) setItems(local);
        } catch {if (request.current()) setItems([]);}
      }
    }
    void load();
    return () => requests.cancel();
  }, [q, requests, detailRequests, invoiceRequests]);
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
  const openDetail = async (id: string) => {
    const request = detailRequests.start(); invoiceRequests.cancel();
    setSelectedSupplierId(id); setDetail(undefined); setInvoiceDetail(undefined);
    try {const result=await eyeApi<any>(`/central/suppliers/${encodeURIComponent(id)}`, {signal:request.signal}); if(request.current())setDetail(result);}
    catch(error:any){if(request.current())setDetail({error:error.message});}
  };
  const openInvoiceDetail = async (sourceHash: string) => {
    const request=invoiceRequests.start();
    try {const result=await eyeApi<any>(`/central/invoices/${encodeURIComponent(sourceHash)}`, {signal:request.signal});if(request.current())setInvoiceDetail(result);}
    catch(error:any){if(request.current())setInvoiceDetail({error:error.message});}
  };
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
