import { useEffect, useState } from "react";
import { Building2, FileSpreadsheet, Search } from "lucide-react";
import { api, eyeApi, euro, shortDate } from "../lib/api";
import { Empty, Loading, PageHeader, Status } from "../components/UI";
import "./marr-data.css";

type Tab = "movements" | "articles" | "prices" | "invoices";
type Summary = { movements?: number; distinct_articles?: number; invoice_numbers?: number; xml_invoices?: number; matched_price_rows?: number; missing_order_dates?: number; credit_notes?: number };
type MarrResponse = { items: Record<string, any>[]; total: number };
type Supplier = { id: string; name: string; filename?: string; source: "marr" | "local" };
const money = (value: unknown) => value == null || value === "" ? "—" : euro(Number(value));

export default function MarrData() {
  const [summary, setSummary] = useState<Summary>();
  const [source, setSource] = useState<{filename?: string; as_of?: string}>({});
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplier, setSupplier] = useState("");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [supplierDetail, setSupplierDetail] = useState<Record<string, any>>();
  const [tab, setTab] = useState<Tab>("articles");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Record<string, any>[]>();
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{summary: Summary; source: {filename?: string; as_of?: string}}>("/marr/summary").then(result => {
      setSummary(result.summary || {}); setSource(result.source || {});
    }).catch(() => setSummary({}));
  }, []);

  useEffect(() => {
    Promise.all([
      api<{items: Supplier[]}>('/marr/suppliers').then(result => (result.items || []).map(item => ({...item, source: "marr" as const}))).catch(() => []),
      eyeApi<any>('/central/suppliers?q=&limit=2000').then(result => (result.items || []).map((item: any) => ({id: String(item.id), name: item.ragione_sociale || "Fornitore senza nome", source: "local" as const}))).catch(() => []),
    ]).then(([marr, local]) => {
      const seen = new Set<string>();
      const available = [...marr, ...local].filter(item => { const key = item.name.trim().toLocaleLowerCase(); if (seen.has(key)) return false; seen.add(key); return true; });
      setSuppliers(available);
      setSupplier(current => current || available[0]?.id || "");
    });
  }, []);

  const selectedSupplier = suppliers.find(item => item.id === supplier);
  const visibleSuppliers = suppliers.filter(item => item.name.toLocaleLowerCase().includes(supplierSearch.toLocaleLowerCase()));

  useEffect(() => {
    if (!selectedSupplier || selectedSupplier.source === "marr") { setSupplierDetail(undefined); return; }
    eyeApi<Record<string, any>>(`/central/suppliers/${encodeURIComponent(selectedSupplier.id)}`).then(setSupplierDetail).catch(() => setSupplierDetail({error: "Dettaglio fornitore non disponibile"}));
  }, [selectedSupplier?.id, selectedSupplier?.source]);

  useEffect(() => {
    let active = true;
    setBusy(true);
    const timer = window.setTimeout(() => {
      const endpoint = tab === "movements" ? "movements" : tab === "articles" ? "articles" : tab === "prices" ? "prices" : "invoices";
      api<MarrResponse>(`/marr/${endpoint}?q=${encodeURIComponent(query)}&limit=200`).then(result => {
        if (active) { setItems(result.items || []); setTotal(result.total || 0); }
      }).catch(() => { if (active) { setItems([]); setTotal(0); } }).finally(() => { if (active) setBusy(false); });
    }, 160);
    return () => { active = false; window.clearTimeout(timer); };
  }, [tab, query]);

  return <>
    <PageHeader title="Dati fornitore" subtitle="Ordini, fatture e prezzi storici dal file MARR 2026">
      <div className="marr-source"><Building2 size={16}/><label htmlFor="marr-supplier-search">Fornitore</label><input id="marr-supplier-search" value={supplierSearch} onChange={event => setSupplierSearch(event.target.value)} placeholder="Cerca fornitore…" list="marr-supplier-options"/><datalist id="marr-supplier-options">{visibleSuppliers.map(item => <option key={item.id} value={item.name}/>)}</datalist><select id="marr-supplier" value={supplier} onChange={event => { setSupplier(event.target.value); setQuery(""); }} disabled={!suppliers.length}><option value="">Seleziona fornitore</option>{visibleSuppliers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{selectedSupplier?.source === "marr" ? <><FileSpreadsheet size={16}/><span>{source.filename || "Snapshot locale"}</span>{source.as_of && <Status tone="ok">Aggiornato al {shortDate(source.as_of)}</Status>}</> : <Status tone="ok">Dati locali</Status>}</div>
    </PageHeader>
    {selectedSupplier?.source !== "marr" && supplierDetail?.supplier && <section className="panel marr-supplier-card"><h2>{supplierDetail.supplier.ragione_sociale}</h2><div className="marr-supplier-meta"><span>Partita IVA: <b>{supplierDetail.supplier.partita_iva || "—"}</b></span><span>Fatture: <b>{supplierDetail.supplier.invoice_count ?? supplierDetail.invoices?.length ?? 0}</b></span><span>Totale: <b>{money(supplierDetail.supplier.total_spent)}</b></span><span>Ultima fattura: <b>{supplierDetail.supplier.last_invoice_date ? shortDate(supplierDetail.supplier.last_invoice_date) : "—"}</b></span></div></section>}
    {selectedSupplier?.source === "marr" && <section className="marr-summary-grid">
      <article><span>Movimenti</span><b>{summary?.movements ?? "—"}</b><small>righe ordine</small></article>
      <article><span>Articoli</span><b>{summary?.distinct_articles ?? "—"}</b><small>codici distinti</small></article>
      <article><span>Prezzi abbinati</span><b>{summary?.matched_price_rows ?? "—"}</b><small>da fatture XML</small></article>
      <article><span>Fatture XML</span><b>{summary?.xml_invoices ?? "—"}</b><small>documenti ricevuti</small></article>
      <article><span>Note di credito</span><b>{summary?.credit_notes ?? "—"}</b><small>movimenti negativi</small></article>
      <article><span>Date ordine mancanti</span><b>{summary?.missing_order_dates ?? "—"}</b><small>da ricostruire</small></article>
    </section>}
    {selectedSupplier?.source !== "marr" && supplierDetail?.invoices?.length ? <section className="panel marr-panel marr-local-detail"><div className="marr-local-title"><h2>Fatture e voci acquistate</h2><span>{supplierDetail.invoices.length} fatture</span></div><div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Imponibile</th><th>Totale</th></tr></thead><tbody>{supplierDetail.invoices.map((row: any) => <tr key={row.id || row.invoice_number}><td>{row.invoice_date ? shortDate(row.invoice_date) : "—"}</td><td><b>{row.invoice_number}</b></td><td>{money(row.taxable)}</td><td>{money(row.total)}</td></tr>)}</tbody></table></div>{supplierDetail.categories?.length ? <div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Acquisti</th><th>Totale</th></tr></thead><tbody>{supplierDetail.categories.map((row: any, index: number) => <tr key={`${row.description}-${index}`}><td>{row.description}</td><td>{row.purchases ?? "—"}</td><td>{money(row.total)}</td></tr>)}</tbody></table></div> : null}</section> : null}
    {selectedSupplier?.source === "marr" && <section className="panel marr-panel">
      <div className="marr-toolbar">
        <div className="marr-tabs" role="tablist" aria-label="Dati fornitore">
          {([["movements", "Dettaglio articoli"], ["articles", "Riepilogo articoli"], ["prices", "Prezzi da fatture"], ["invoices", "Fatture ricevute"]] as [Tab, string][]).map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        <label className="marr-search"><Search size={16}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder={tab === "movements" ? "Cerca articolo, ordine o fattura…" : tab === "articles" ? "Cerca articolo o codice…" : tab === "prices" ? "Cerca prodotto, fattura o codice…" : "Cerca fattura o XML…"}/></label>
      </div>
      {busy && <Loading/>}
      {!busy && !items?.length && <Empty title="Nessun dato trovato" text="Modifica la ricerca o seleziona un'altra vista."/>}
      {!busy && !!items?.length && tab === "movements" && <div className="table-wrap"><table><thead><tr><th>Articolo (Descrizione)</th><th>Quantità</th><th>UM</th><th>Data ordine</th><th>Cod. articolo</th><th>N. ordine</th><th>N. fattura</th><th>Data fattura</th><th>Tipo documento</th><th>Note</th></tr></thead><tbody>{items.map((row, index) => <tr key={`${row.order_number}-${row.article_code}-${index}`}><td>{row.description}</td><td>{row.quantity ?? "—"}</td><td>{row.unit || "—"}</td><td>{row.order_date ? shortDate(row.order_date) : "—"}</td><td><b>{row.article_code || "—"}</b></td><td>{row.order_number || "—"}</td><td>{row.invoice_number || "—"}</td><td>{row.invoice_date ? shortDate(row.invoice_date) : "—"}</td><td>{row.document_type || "—"}</td><td>{row.notes || "—"}</td></tr>)}</tbody></table></div>}
      {!busy && !!items?.length && tab === "articles" && <div className="table-wrap"><table><thead><tr><th>Codice</th><th>Articolo</th><th>UM</th><th>Quantità totale</th><th>Movimenti</th><th>Primo ordine</th><th>Ultimo ordine</th></tr></thead><tbody>{items.map(row => <tr key={`${row.article_code}-${row.description}`}><td><b>{row.article_code}</b></td><td>{row.description}</td><td>{row.unit || "—"}</td><td>{row.total_quantity ?? "—"}</td><td>{row.movement_count ?? "—"}</td><td>{row.first_order ? shortDate(row.first_order) : "—"}</td><td>{row.last_order ? shortDate(row.last_order) : "—"}</td></tr>)}</tbody></table></div>}
      {!busy && !!items?.length && tab === "prices" && <div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Codice</th><th>Descrizione</th><th>Quantità</th><th>UM</th><th>Prezzo unitario</th><th>Totale riga</th><th>XML</th></tr></thead><tbody>{items.map((row, index) => <tr key={`${row.invoice_number}-${row.article_code}-${index}`}><td>{row.invoice_date ? shortDate(row.invoice_date) : "—"}</td><td><b>{row.invoice_number}</b></td><td>{row.article_code}</td><td>{row.description}</td><td>{row.quantity ?? "—"}</td><td>{row.unit || "—"}</td><td>{money(row.unit_price)}</td><td>{money(row.line_total)}</td><td>{row.xml_file || "—"}</td></tr>)}</tbody></table></div>}
      {!busy && !!items?.length && tab === "invoices" && <div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Tipo</th><th>Righe prodotto</th><th>Totale</th><th>XML</th><th>Stato</th></tr></thead><tbody>{items.map((row, index) => <tr key={`${row.invoice_number}-${index}`}><td>{row.invoice_date ? shortDate(row.invoice_date) : "—"}</td><td><b>{row.invoice_number}</b></td><td>{row.document_type || "—"}</td><td>{row.product_rows ?? "—"}</td><td>{money(row.invoice_total)}</td><td>{row.xml_file || "—"}</td><td>{row.reconciliation_status || "Da ricalcolare"}</td></tr>)}</tbody></table></div>}
      {!busy && !!items?.length && <div className="marr-result-count">Visualizzati {items.length} di {total} record</div>}
    </section>}
  </>;
}
