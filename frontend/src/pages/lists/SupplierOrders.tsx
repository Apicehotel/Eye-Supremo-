import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { eyeApi, eyeBlob, euro, shortDate } from "../../lib/api";
import { Empty, Loading } from "../../components/UI";
import { csvOf } from "../../lib/csv";

type Row = (string | number | null | undefined)[];
type Tab = "deliveries" | "movements" | "summary" | "checks" | "prices" | "invoices" | "xml";
const TABS: [Tab, string][] = [
  ["deliveries", "Consegne giornaliere"], ["movements", "Dettaglio articoli"], ["summary", "Riepilogo per articolo"],
  ["checks", "Verifiche"], ["prices", "Prezzi da fatture"], ["invoices", "Fatture ricevute"], ["xml", "Controlli XML"],
];
const MONTHS = ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"];

function download(name: string, rows: Row[]) {
  const url = URL.createObjectURL(new Blob(["﻿" + csvOf(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}
const qty = (n: number) => Number.isInteger(n) ? String(n) : n.toLocaleString("it-IT", { maximumFractionDigits: 3 });
const day = (iso: string) => shortDate(iso);

export function SupplierOrders({ supplier }: { supplier: string }) {
  const [tab, setTab] = useState<Tab>("deliveries");
  const [year, setYear] = useState<number>();
  const [month, setMonth] = useState<number>(new Date().getMonth());
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string>();
  const [filter, setFilter] = useState("");
  const [article, setArticle] = useState<any>();
  const [message, setMessage] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback((signal?: AbortSignal) => {
    setError(undefined);
    return eyeApi<any>(`/central/supplier-orders?supplier=${encodeURIComponent(supplier)}${year ? `&year=${year}` : ""}`, { signal })
      .then(setData).catch((e) => { if (!signal?.aborted) setError(String(e?.message || e)); });
  }, [supplier, year]);
  useEffect(() => { const c = new AbortController(); setData(undefined); setArticle(undefined); load(c.signal); return () => c.abort(); }, [load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const body = new FormData(); body.append("file", files[0]);
    setMessage("Caricamento…");
    try {
      const r: any = await eyeApi(`/central/supplier-orders/import?supplier=${encodeURIComponent(supplier)}`, { method: "POST", body });
      setMessage(`Foglio caricato: ${r.movements} movimenti, ${r.price_rows} righe prezzo, ${r.invoices} fatture.`);
      setData(undefined); await load();
    } catch (e: any) { setMessage(String(e?.message || e)); }
    finally { if (input.current) input.current.value = ""; }
  }
  async function exportExcel() {
    try {
      const blob = await eyeBlob(`/central/supplier-orders/export?supplier=${encodeURIComponent(supplier)}${data?.deliveries?.year ? `&year=${data.deliveries.year}` : ""}`);
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `Ordini_${supplier.replace(/[^A-Za-z0-9._-]+/g, "_")}.xlsx`; a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { setMessage(String(e?.message || e)); }
  }
  async function openArticle(code: string) {
    try { setArticle(await eyeApi<any>(`/central/supplier-orders/article?supplier=${encodeURIComponent(supplier)}&code=${encodeURIComponent(code)}`)); } catch (e: any) { setMessage(String(e?.message || e)); }
  }

  const needle = filter.trim().toLowerCase();
  const match = (text: string) => !needle || text.toLowerCase().includes(needle);
  const days = useMemo(() => {
    const y = data?.deliveries?.year; if (!y) return [] as string[];
    const n = new Date(y, month + 1, 0).getDate();
    return Array.from({ length: n }, (_, i) => `${y}-${String(month + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`);
  }, [data, month]);

  const uploader = <div className="button-row">
    <input ref={input} type="file" accept=".xlsx" hidden onChange={(e) => upload(e.target.files)} />
    <button className="secondary-btn" onClick={() => input.current?.click()}>Usa un mio foglio ordini (.xlsx, facoltativo)</button>
    {data?.source === "sheet" && <button className="secondary-btn" onClick={exportExcel}>Scarica Excel</button>}
    {message && <span role="status">{message}</span>}
  </div>;

  if (error) return <><Empty title="Ordini non disponibili" text={error} />{uploader}</>;
  if (!data) return <Loading />;
  const c = data.checks || {};
  if (!c.movements) return <><Empty title="Nessun ordine per questo fornitore" text="Non risultano fatture di questo fornitore né in archivio né nel centrale. Controlla che l'archivio sia sincronizzato (Impostazioni → Archivio centrale)." />{uploader}</>;
  const sheet = data.source === "sheet";

  return (
    <div className="supplier-orders">
      <div className="panel-title"><h3>Ordini · {supplier}</h3></div>
      {uploader}
      {!sheet && c.invoices_without_rows > 0 && <p className="muted" role="status">{c.invoices_without_rows} fatture non hanno ancora le righe scaricate dal centrale: riapri la pagina tra poco per completare i dati.</p>}
      <p className="muted">{sheet ? `Foglio: ${data.filename || "caricato"} · data di riferimento: data ordine; se mancante, data fattura.` : "Calcolato dalle fatture in cache (data fattura). Per numero ordine, DDT e codici carica il foglio ordini."}</p>
      <div className="button-row" role="tablist">
        {TABS.filter(([k]) => sheet || !["xml"].includes(k)).map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "primary-btn" : "secondary-btn"} onClick={() => { setTab(key); setArticle(undefined); }}>{label}</button>)}
      </div>
      {tab !== "checks" && tab !== "xml" && <input aria-label="Filtra" placeholder="Filtra articolo o fattura…" value={filter} onChange={(e) => setFilter(e.target.value)} />}

      {article && <article className="panel detail-panel">
        <div className="panel-title"><h3>↩ {article.article}</h3><button className="secondary-btn" onClick={() => setArticle(undefined)}>Torna alle consegne</button></div>
        <p><b>Codice:</b> {article.code} · <b>Unità:</b> {article.unit} · <b>Quantità netta:</b> {qty(article.net_quantity)} · <b>Resi:</b> {qty(article.credited_quantity)} · <b>Movimenti:</b> {article.movements.length} · <b>Senza data ordine:</b> {article.without_order_date}</p>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Quantità</th><th>Prezzo unit.</th><th>Fattura</th><th>N. ordine</th></tr></thead>
          <tbody>{article.movements.map((m: any, i: number) => <tr key={i} style={m.credit ? { background: "#fde2e2" } : m.uses_invoice_date ? { background: "#fff6bf" } : undefined}><td>{m.date ? day(m.date) : "—"}</td><td>{qty(m.quantity)}</td><td>{m.unit_price != null ? euro(m.unit_price) : "—"}</td><td>{m.invoice_number}</td><td>{m.order_number}</td></tr>)}</tbody></table></div>
        <p><small>Giallo = data fattura (data ordine mancante) · Rosso = nota di credito / reso</small></p>
      </article>}

      {!article && tab === "deliveries" && <>
        <label>Anno <select value={data.deliveries.year ?? ""} onChange={(e) => setYear(Number(e.target.value))}>{data.deliveries.years.map((y: number) => <option key={y} value={y}>{y}</option>)}</select></label>{" "}
        <label>Mese <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>{MONTHS.map((m, i) => <option key={m} value={i}>{m}</option>)}</select></label>
        <button className="secondary-btn" onClick={() => { const all = [...new Set<string>(data.deliveries.rows.flatMap((r: any) => Object.keys(r.days)))].sort(); download(`consegne-${data.deliveries.year}.csv`, [["Articolo", "UM", ...all], ...data.deliveries.rows.flatMap((r: any) => [[r.article, r.unit, ...all.map((d) => r.days[d] ?? "")], ["   ↳ Prezzo unitario", "", ...all.map((d) => r.prices?.[d] ?? "")]])]); }}>Scarica CSV (anno)</button>
        <p><small>Clicca sull'articolo per il dettaglio. Giallo = data fattura (data ordine mancante) · Rosso = reso. Sotto ogni articolo il prezzo da fattura.</small></p>
        <div className="table-wrap"><table><thead><tr><th>ARTICOLO / PRODOTTO (sotto: prezzo)</th>{days.map((d) => <th key={d}>{Number(d.slice(8))}</th>)}</tr></thead>
          <tbody>{data.deliveries.rows.filter((r: any) => match(r.article)).flatMap((r: any) => [
            <tr key={r.article}><td><button className="link-btn" onClick={() => openArticle(r.code || r.article)} style={{ border: 0, background: "transparent", padding: 0, font: "inherit", textDecoration: "underline", cursor: "pointer" }}>{r.article}</button></td>
              {days.map((d) => { const v = r.days[d]; return <td key={d} style={v == null ? undefined : v < 0 ? { background: "#fde2e2" } : (r.invoice_date_days || []).includes(d) ? { background: "#fff6bf" } : undefined}>{v != null ? qty(v) : ""}</td>; })}</tr>,
            <tr key={r.article + "-p"}><td><small>↳ Prezzo unitario (€/ {r.unit})</small></td>{days.map((d) => <td key={d}><small>{r.prices?.[d] != null ? euro(r.prices[d]) : ""}</small></td>)}</tr>,
          ])}</tbody></table></div></>}

      {!article && tab === "movements" && <>
        <button className="secondary-btn" onClick={() => download("dettaglio-articoli.csv", [["Articolo", "Quantità", "UM", "Data ordine", "Cod. articolo", "N. ordine", "N. fattura", "Data fattura", "Tipo documento", "Prezzo unit."], ...data.movements.map((m: any) => [m.article, m.quantity, m.unit, m.order_date ?? (sheet ? "" : m.date), m.code, m.order_number, m.invoice_number, m.invoice_date ?? m.date, m.document_type, m.unit_price])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>Quantità</th><th>UM</th><th>Data ordine</th><th>Cod. articolo</th><th>N. ordine</th><th>N. fattura</th><th>Data fattura</th><th>Tipo documento</th><th>Prezzo unit.</th></tr></thead>
          <tbody>{data.movements.filter((m: any) => match(`${m.article} ${m.invoice_number} ${m.code || ""}`)).map((m: any, i: number) => <tr key={i}><td>{m.article}</td><td>{qty(m.quantity)}</td><td>{m.unit}</td><td>{m.order_date ? day(m.order_date) : "—"}</td><td>{m.code || "—"}</td><td>{m.order_number || "—"}</td><td>{m.invoice_number}</td><td>{m.invoice_date ? day(m.invoice_date) : m.date ? day(m.date) : "—"}</td><td>{m.document_type}</td><td>{m.unit_price ? euro(m.unit_price) : "—"}</td></tr>)}</tbody></table></div></>}

      {!article && tab === "summary" && <>
        <button className="secondary-btn" onClick={() => download("riepilogo-articoli.csv", [["Articolo", "Cod. articolo", "UM", "Quantità totale (netta)", "di cui resi", "N. righe", "Primo ordine", "Ultimo ordine"], ...data.summary.map((r: any) => [r.article, r.code, r.unit, r.net_quantity, r.credited_quantity, r.rows, r.first_date, r.last_date])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>Cod. articolo</th><th>UM</th><th>Quantità totale (netta)</th><th>di cui resi</th><th>N. righe</th><th>Primo ordine</th><th>Ultimo ordine</th></tr></thead>
          <tbody>{data.summary.filter((r: any) => match(`${r.article} ${r.code || ""}`)).map((r: any) => <tr key={r.article + r.code}><td>{r.article}</td><td>{r.code || "—"}</td><td>{r.unit}</td><td>{qty(r.net_quantity)}</td><td>{r.credited_quantity ? qty(r.credited_quantity) : "—"}</td><td>{r.rows}</td><td>{r.first_date ? day(r.first_date) : "—"}</td><td>{r.last_date ? day(r.last_date) : "—"}</td></tr>)}</tbody></table></div></>}

      {!article && tab === "checks" && <>
        <div className="kpi-grid">
          <div><span>Articoli distinti (codici)</span><b>{c.distinct_articles}</b></div><div><span>Movimenti</span><b>{c.movements}</b></div>
          <div><span>Date ordine mancanti</span><b>{c.undated_movements}</b></div><div><span>Note di credito</span><b>{c.credit_notes}</b></div>
          {sheet && <><div><span>Fatture XML elaborate</span><b>{c.invoices}</b></div><div><span>Righe prezzo inserite</span><b>{c.price_rows}</b></div></>}
        </div>
        <p><small>Criterio: data ordine; in sua assenza, data fattura. I resi (note di credito) sono quantità negative.</small></p>
        {sheet && <div className="table-wrap"><table><thead><tr><th>Riga origine</th><th>Codice</th><th>Articolo</th><th>Quantità</th><th>UM</th><th>Data utilizzata</th><th>Tipo documento</th><th>Motivo verifica</th></tr></thead>
          <tbody>{(c.verify_rows || []).map((r: any) => <tr key={r.origin_row}><td>{r.origin_row}</td><td>{r.code}</td><td>{r.article}</td><td>{qty(r.quantity)}</td><td>{r.unit}</td><td>{r.date_used ? day(r.date_used) : "—"}</td><td>{r.document_type}</td><td>{r.reason}</td></tr>)}</tbody></table></div>}</>}

      {!article && tab === "prices" && (sheet ? <>
        <button className="secondary-btn" onClick={() => download("prezzi-da-fatture.csv", [["Data fattura", "Numero fattura", "Data DDT", "Tipo doc.", "Codice articolo", "Descrizione", "Quantità (+/-)", "UM", "Prezzo unit. €", "Totale riga (+/-) €", "IVA %", "File XML", "Riga fattura"], ...data.prices.map((p: any) => [p.invoice_date, p.invoice_number, p.ddt_date, p.doc_type, p.code, p.description, p.quantity, p.unit, p.unit_price, p.line_total, p.vat_rate, p.xml_file, p.invoice_line])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Data fattura</th><th>Numero</th><th>Data DDT</th><th>Tipo</th><th>Codice</th><th>Descrizione</th><th>Quantità</th><th>UM</th><th>Prezzo unit. €</th><th>Totale riga €</th><th>IVA %</th></tr></thead>
          <tbody>{data.prices.filter((p: any) => match(`${p.description} ${p.invoice_number} ${p.code}`)).map((p: any, i: number) => <tr key={i}><td>{p.invoice_date ? day(p.invoice_date) : "—"}</td><td>{p.invoice_number}</td><td>{p.ddt_date ? day(p.ddt_date) : "—"}</td><td>{p.doc_type}</td><td>{p.code}</td><td>{p.description}</td><td>{qty(p.quantity)}</td><td>{p.unit}</td><td>{p.unit_price != null ? euro(p.unit_price) : "—"}</td><td>{p.line_total != null ? euro(p.line_total) : "—"}</td><td>{p.vat_rate ?? "—"}</td></tr>)}</tbody></table></div></> : <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>Ultima data</th><th>Ultimo prezzo</th><th>Minimo</th><th>Massimo</th><th>Normalizzato</th></tr></thead>
          <tbody>{data.prices.filter((p: any) => match(p.article)).map((p: any) => <tr key={p.article}><td>{p.article}</td><td>{day(p.last_date)}</td><td>{euro(p.last_price)}</td><td>{euro(p.min_price)}</td><td>{euro(p.max_price)}</td><td>{p.last_normalized_price != null ? `${euro(Number(p.last_normalized_price))} / ${p.normalized_unit}` : "—"}</td></tr>)}</tbody></table></div>)}

      {!article && tab === "invoices" && <>
        <button className="secondary-btn" onClick={() => download("fatture-ricevute.csv", [["Data fattura", "Numero fattura", "Data DDT", "Tipo", "Righe prodotto", "Imponibile da righe €", "IVA riepilogo €", "Totale fattura €", "XML origine", "Esito quadratura", "Differenza €"], ...data.invoices.map((i: any) => [i.invoice_date, i.invoice_number, i.ddt_date, i.doc_type ?? i.type, i.product_rows, i.rows_amount, i.vat, i.total, i.xml_file ?? i.source_filename, i.outcome, i.difference])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Data fattura</th><th>Numero</th><th>Data DDT</th><th>Tipo</th><th>Righe prodotto</th><th>Imponibile da righe €</th><th>IVA €</th><th>Totale €</th><th>Esito quadratura</th><th>Differenza €</th></tr></thead>
          <tbody>{data.invoices.filter((i: any) => match(i.invoice_number || "")).map((i: any) => <tr key={`${i.invoice_number}-${i.invoice_date}`} style={i.outcome === "VERIFICARE" || i.outcome === "Differenza" ? { background: "#fff6bf" } : undefined}><td>{i.invoice_date ? day(i.invoice_date) : "—"}</td><td>{i.invoice_number}</td><td>{i.ddt_date ? day(i.ddt_date) : "—"}</td><td>{i.doc_type ?? i.type}</td><td>{i.product_rows}</td><td>{euro(i.rows_amount)}</td><td>{i.vat != null ? euro(i.vat) : "—"}</td><td>{euro(i.total)}</td><td>{i.outcome}</td><td>{i.difference != null ? euro(i.difference) : "—"}</td></tr>)}</tbody></table></div></>}

      {!article && tab === "xml" && <>
        <div className="kpi-grid">
          <div><span>Fatture XML ricevute</span><b>{c.invoices}</b></div><div><span>Righe articoli con prezzo</span><b>{c.price_rows}</b></div>
          <div><span>Movimenti nel dettaglio</span><b>{c.movements}</b></div><div><span>Prezzi ancora mancanti</span><b>{c.missing_prices}</b></div>
          <div><span>Numeri fattura ancora da ricevere</span><b>{c.missing_xml_invoices}</b></div><div><span>Scostamenti quantità / fattura</span><b>{c.quantity_mismatches}</b></div>
        </div>
        <h4>Fatture presenti nel Dettaglio articoli per cui non è ancora stato fornito il file XML</h4>
        <button className="secondary-btn" onClick={() => download("fatture-senza-xml.csv", [["N. fattura mancante", "Data fattura", "Movimenti", "Note", "XML ricevuto?"], ...data.xml_checks.map((r: any) => [r.invoice_number, r.invoice_date, r.movements, r.note, "NO"])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>N. fattura mancante</th><th>Data fattura</th><th>Movimenti</th><th>Note</th><th>XML ricevuto?</th></tr></thead>
          <tbody>{data.xml_checks.map((r: any) => <tr key={r.invoice_number}><td>{r.invoice_number}</td><td>{r.invoice_date ? day(r.invoice_date) : "—"}</td><td>{r.movements}</td><td>{r.note}</td><td>NO</td></tr>)}</tbody></table></div></>}
    </div>
  );
}
