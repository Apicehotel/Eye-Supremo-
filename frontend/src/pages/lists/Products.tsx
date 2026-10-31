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
export function Products() {
  const [items, setItems] = useState<any[]>(),
    [configs, setConfigs] = useState<Record<string, any>>({}),
    [tracking, setTracking] = useState<Record<string, boolean>>({}),
    [q, setQ] = useState(""),
    [pageSize, setPageSize] = useState(50),
    [page, setPage] = useState(0),
    [sort, setSort] = useState<{key: SortKey; direction: SortDirection}>({key: "nome_canonico", direction: "asc"}),
    [detail, setDetail] = useState<any>(),
    [invoiceRef, setInvoiceRef] = useState<InvoiceRefTarget>(),
    [configuredName, setConfiguredName] = useState(""),
    [manufacturer, setManufacturer] = useState(""),
    [piecesPerPack, setPiecesPerPack] = useState(""),
    [configSaved, setConfigSaved] = useState(false),
    [tracked, setTracked] = useState(false);
  const productsRequest = useLatestRequest();
  const [selected, setSelected] = useState<Record<string, string[]>>({}),
    [reloadTick, setReloadTick] = useState(0);
  const selectedKeys = Object.keys(selected);
  async function mergeSelected() {
    const names = selectedKeys.flatMap((k) => selected[k]);
    await eyeApi("/product-groups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names }) });
    setSelected({});
    setReloadTick((t) => t + 1);
  }
  async function splitItem(p: any) {
    for (const n of p.canonical_names || []) await eyeApi(`/product-groups?name=${encodeURIComponent(n)}`, { method: "DELETE" });
    setReloadTick((t) => t + 1);
  }
  useEffect(() => {
    api<Record<string, any>>("/product-config").then(setConfigs).catch(() => setConfigs({}));
    api<Record<string, boolean>>("/product-tracking").then(setTracking).catch(() => setTracking({}));
  }, []);
  useEffect(() => {
    setPage(0);
    // Attesa breve mentre si digita: una richiesta per parola, non una per lettera.
    const timer = window.setTimeout(() => {
      const request = productsRequest.start();
      setItems(undefined);
      api<any[]>(`/products?q=${encodeURIComponent(q)}&limit=200`, {signal:request.signal}).then((result) => {
        if (request.current()) setItems(result);
      }).catch(() => {
        if (request.current()) setItems([]);
      });
    }, q.trim() ? 250 : 0);
    return () => { window.clearTimeout(timer); productsRequest.cancel(); };
  }, [q, reloadTick, productsRequest]);
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
      setPiecesPerPack(configs[name]?.pieces_per_pack ? String(configs[name].pieces_per_pack) : "");
      setTracked(Boolean(tracking[name]));
      setConfigSaved(false);
    } catch {
      setDetail({ error: "Dettaglio prodotto non disponibile" });
    }
  }
  async function saveProductConfig() {
    if (!detail?.sourceName || !configuredName.trim()) return;
    const saved = await api<any>("/product-config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_name: detail.sourceName, configured_name: configuredName.trim(), manufacturer: manufacturer.trim(), pieces_per_pack: Number(piecesPerPack.replace(",", ".")) || null }) });
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
      <InvoiceViewer target={invoiceRef} onClose={() => setInvoiceRef(undefined)} />
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
        {selectedKeys.length >= 2 && (
          <div className="screen-only" style={{ padding: "8px 12px" }}>
            <button type="button" onClick={mergeSelected}>Unisci {selectedKeys.length} selezionati in un solo prodotto</button>{" "}
            <button type="button" onClick={() => setSelected({})}>Annulla</button>
          </div>
        )}
        {!items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                    <tr>
                      <th title="Seleziona più voci per unirle"></th>
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
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label="Seleziona per unire" checked={p.nome_canonico in selected} onChange={(e) => setSelected((cur) => { const next = { ...cur }; if (e.target.checked) next[p.nome_canonico] = p.canonical_names || [p.nome_canonico]; else delete next[p.nome_canonico]; return next; })} />
                    </td>
                    <td>
                      <b>{configs[p.nome_canonico]?.configured_name || p.nome_canonico}</b>
                      {p.user_group && <small className="recognized-tag" onClick={(e) => e.stopPropagation()}> {p.canonical_names.length} nomi uniti <button type="button" onClick={() => splitItem(p)}>separa</button></small>}
                    </td>
                    <td data-label="Categoria">{p.categoria || "—"}</td>
                    <td data-label="Marca">{configs[p.nome_canonico]?.manufacturer || p.marca || p.recognition?.brand || "—"}{p.recognition?.category && <small className="recognized-tag" title="Riconosciuto da Open Food Facts">{[p.recognition.category, p.recognition.subcategory].filter(Boolean).join(" › ")}</small>}</td>
                    <td data-label="Acquisti">{p.purchases}</td>
                    <td data-label="Minimo">{p.min_price ? euro(p.min_price) : "—"}</td>
                    <td data-label="Media">{p.avg_price ? euro(p.avg_price) : "—"}</td>
                    <td data-label="Massimo">{p.max_price ? euro(p.max_price) : "—"}</td>
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
            <div className="product-config"><h3>Configurazione prodotto</h3><div className="product-config-grid"><label>Nome visualizzato<input value={configuredName} onChange={e => setConfiguredName(e.target.value)} /></label><label>Produttore<input value={manufacturer} onChange={e => setManufacturer(e.target.value)} placeholder="Produttore / marca" /></label><label>Pezzi per confezione<input inputMode="decimal" value={piecesPerPack} onChange={e => setPiecesPerPack(e.target.value)} placeholder="es. 6 (per cartone)" title="Quanti pezzi contiene ogni unità acquistata: il report calcola il prezzo al pezzo" /></label></div><button className="primary-btn" onClick={saveProductConfig} disabled={!configuredName.trim()}>Salva configurazione</button>{configSaved && <span className="success">Configurazione salvata</span>}<label className="product-track-toggle"><input type="checkbox" checked={tracked} onChange={e => saveTracking(e.target.checked)} /> Monitora questo prodotto e segnala variazioni di prezzo</label></div>
            <p><b>Acquisti:</b> {detail.product?.purchases ?? 0} · <b>Prezzo medio:</b> {detail.product?.avg_price != null ? euro(Number(detail.product.avg_price)) : "—"}</p>
            {detail.history?.length ? <div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Fornitore</th><th>Quantità</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th><th>Totale</th><th>Fattura</th></tr></thead><tbody>{detail.history.map((h: any, i: number) => <tr key={`${h.source_hash}-${i}`}><td>{shortDate(h.invoice_date)}</td><td>{h.invoice_number}</td><td>{h.supplier_name}</td><td>{h.quantity ?? "—"} {h.original_unit || h.normalized_unit || ""}</td><td>{h.unit_price != null ? euro(Number(h.unit_price)) : "—"}</td><td>{h.normalized_price != null ? `${euro(Number(h.normalized_price))} / ${h.normalized_unit || h.original_unit || "unità"}` : "—"}</td><td>{h.line_total != null ? euro(Number(h.line_total)) : "—"}</td><td><OpenInvoiceButton id={h.source_hash} highlight={detail.product?.canonical_name} onOpen={setInvoiceRef} /></td></tr>)}</tbody></table></div> : <p>Nessun acquisto collegato.</p>}
          </>}
        </article>
      )}
    </>
  );
}
