import { useEffect, useMemo, useState } from "react";
import { eyeApi, euro, shortDate } from "../../lib/api";
import { Empty, Loading } from "../../components/UI";
import { csvOf } from "../../lib/csv";

type Section = "summary" | "movements" | "deliveries" | "prices" | "invoices" | "checks";
const SECTIONS: [Section, string][] = [
  ["summary", "Riepilogo articoli"], ["movements", "Dettaglio"], ["deliveries", "Consegne giornaliere"],
  ["prices", "Prezzi da fatture"], ["invoices", "Fatture ricevute"], ["checks", "Verifiche"],
];

function download(name: string, rows: (string | number | null | undefined)[][]) {
  const url = URL.createObjectURL(new Blob(["﻿" + csvOf(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}

const qty = (n: number) => Number.isInteger(n) ? String(n) : n.toLocaleString("it-IT", { maximumFractionDigits: 3 });

export function SupplierOrders({ supplier }: { supplier: string }) {
  const [section, setSection] = useState<Section>("summary");
  const [year, setYear] = useState<number>();
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string>();
  const [filter, setFilter] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError(undefined);
    eyeApi<any>(`/central/supplier-orders?supplier=${encodeURIComponent(supplier)}${year ? `&year=${year}` : ""}`, { signal: controller.signal })
      .then(setData).catch((e) => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, [supplier, year]);
  const needle = filter.trim().toLowerCase();
  const match = (text: string) => !needle || text.toLowerCase().includes(needle);
  const days = useMemo(() => {
    if (!data?.deliveries?.rows) return [] as string[];
    return [...new Set<string>(data.deliveries.rows.flatMap((r: any) => Object.keys(r.days)))].sort();
  }, [data]);
  if (error) return <Empty title="Ordini non disponibili" text={error} />;
  if (!data) return <Loading />;
  const c = data.checks || {};
  if (!c.movements) return <Empty title="Nessun articolo in cache" text="Per questo fornitore non ci sono righe fattura nella cache del PC. Usa «Scarica tutto per offline» in Impostazioni → Sincronizzazione." />;
  return (
    <div className="supplier-orders">
      <div className="panel-title"><h3>Ordini · {supplier}</h3></div>
      <p className="muted">Data di riferimento: data fattura. Numero ordine, data ordine, DDT e codice articolo non sono nei dati importati.</p>
      <div className="button-row" role="tablist">
        {SECTIONS.map(([key, label]) => <button key={key} role="tab" aria-selected={section === key} className={section === key ? "primary-btn" : "secondary-btn"} onClick={() => setSection(key)}>{label}</button>)}
      </div>
      {section !== "checks" && <input aria-label="Filtra articoli" placeholder="Filtra…" value={filter} onChange={(e) => setFilter(e.target.value)} />}
      {section === "summary" && <>
        <button className="secondary-btn" onClick={() => download("riepilogo-articoli.csv", [["Articolo", "UM", "Quantità netta", "Resi", "Righe", "Primo", "Ultimo"], ...data.summary.map((r: any) => [r.article, r.unit, r.net_quantity, r.credited_quantity, r.rows, r.first_date, r.last_date])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>UM</th><th>Quantità netta</th><th>di cui resi</th><th>Righe</th><th>Primo</th><th>Ultimo</th></tr></thead>
          <tbody>{data.summary.filter((r: any) => match(r.article)).map((r: any) => <tr key={r.article}><td>{r.article}</td><td>{r.unit}</td><td>{qty(r.net_quantity)}</td><td>{r.credited_quantity ? qty(r.credited_quantity) : "—"}</td><td>{r.rows}</td><td>{r.first_date ? shortDate(r.first_date) : "—"}</td><td>{r.last_date ? shortDate(r.last_date) : "—"}</td></tr>)}</tbody></table></div></>}
      {section === "movements" && <>
        <button className="secondary-btn" onClick={() => download("dettaglio-articoli.csv", [["Articolo", "Quantità", "UM", "Data", "Fattura", "Tipo", "Prezzo unit.", "Totale riga"], ...data.movements.map((m: any) => [m.article, m.quantity, m.unit, m.date, m.invoice_number, m.document_type, m.unit_price, m.line_total])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>Quantità</th><th>UM</th><th>Data</th><th>Fattura</th><th>Tipo</th><th>Prezzo unit.</th><th>Prezzo normalizzato</th></tr></thead>
          <tbody>{data.movements.filter((m: any) => match(m.article)).map((m: any, i: number) => <tr key={i}><td>{m.article}</td><td>{qty(m.quantity)}</td><td>{m.unit}</td><td>{m.date ? shortDate(m.date) : "—"}</td><td>{m.invoice_number}</td><td>{m.document_type}</td><td>{euro(m.unit_price)}</td><td>{m.normalized_price != null ? `${euro(Number(m.normalized_price))} / ${m.normalized_unit}` : "—"}</td></tr>)}</tbody></table></div></>}
      {section === "deliveries" && <>
        <label>Anno <select value={data.deliveries.year ?? ""} onChange={(e) => setYear(Number(e.target.value))}>{data.deliveries.years.map((y: number) => <option key={y} value={y}>{y}</option>)}</select></label>
        <button className="secondary-btn" onClick={() => download(`consegne-${data.deliveries.year}.csv`, [["Articolo", "UM", ...days], ...data.deliveries.rows.map((r: any) => [r.article, r.unit, ...days.map((d) => r.days[d] ?? "")])])}>Scarica CSV</button>
        {days.length ? <div className="table-wrap"><table><thead><tr><th>Articolo</th>{days.map((d) => <th key={d}>{shortDate(d)}</th>)}</tr></thead>
          <tbody>{data.deliveries.rows.filter((r: any) => match(r.article)).map((r: any) => <tr key={r.article}><td>{r.article} <small>{r.unit}</small></td>{days.map((d) => <td key={d}>{r.days[d] != null ? qty(r.days[d]) : ""}</td>)}</tr>)}</tbody></table></div> : <p>Nessuna consegna nell'anno scelto.</p>}</>}
      {section === "prices" && <>
        <button className="secondary-btn" onClick={() => download("prezzi-da-fatture.csv", [["Articolo", "UM", "Righe", "Ultima data", "Ultimo prezzo", "Minimo", "Massimo", "Prezzo normalizzato", "Unità"], ...data.prices.map((p: any) => [p.article, p.unit, p.rows, p.last_date, p.last_price, p.min_price, p.max_price, p.last_normalized_price, p.normalized_unit])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Articolo</th><th>Ultima data</th><th>Ultimo prezzo</th><th>Minimo</th><th>Massimo</th><th>Normalizzato</th></tr></thead>
          <tbody>{data.prices.filter((p: any) => match(p.article)).map((p: any) => <tr key={p.article} title={p.history.map((h: any) => `${h.date}: ${h.price}`).join("\n")}><td>{p.article}</td><td>{shortDate(p.last_date)}</td><td>{euro(p.last_price)}</td><td>{euro(p.min_price)}</td><td>{euro(p.max_price)}</td><td>{p.last_normalized_price != null ? `${euro(Number(p.last_normalized_price))} / ${p.normalized_unit}` : "—"}</td></tr>)}</tbody></table></div></>}
      {section === "invoices" && <>
        <button className="secondary-btn" onClick={() => download("fatture-ricevute.csv", [["Data", "Numero", "Tipo", "Righe prodotto", "Imponibile da righe", "Imponibile", "IVA", "Totale", "Esito", "Differenza"], ...data.invoices.map((i: any) => [i.invoice_date, i.invoice_number, i.type, i.product_rows, i.rows_amount, i.taxable, i.vat, i.total, i.outcome, i.difference])])}>Scarica CSV</button>
        <div className="table-wrap"><table><thead><tr><th>Data</th><th>Numero</th><th>Tipo</th><th>Righe</th><th>Imponibile da righe</th><th>IVA</th><th>Totale</th><th>Esito</th></tr></thead>
          <tbody>{data.invoices.filter((i: any) => match(`${i.invoice_number} ${i.type}`)).map((i: any) => <tr key={`${i.invoice_number}-${i.invoice_date}`}><td>{i.invoice_date ? shortDate(i.invoice_date) : "—"}</td><td>{i.invoice_number}</td><td>{i.type}</td><td>{i.product_rows}</td><td>{euro(i.rows_amount)}</td><td>{i.vat != null ? euro(i.vat) : "—"}</td><td>{euro(i.total)}</td><td>{i.outcome}{i.difference ? ` (${euro(i.difference)})` : ""}</td></tr>)}</tbody></table></div></>}
      {section === "checks" && <div className="kpi-grid">
        <div><span>Articoli distinti</span><b>{c.distinct_articles}</b></div><div><span>Movimenti</span><b>{c.movements}</b></div>
        <div><span>Fatture</span><b>{c.invoices}</b></div><div><span>Note di credito</span><b>{c.credit_notes}</b></div>
        <div><span>Fatture che quadrano</span><b>{c.invoices_balanced}</b></div><div><span>Con differenza</span><b>{c.invoices_with_difference}</b></div>
        <div><span>Senza dati per la quadratura</span><b>{c.invoices_without_data}</b></div><div><span>Movimenti senza data</span><b>{c.undated_movements}</b></div>
        <p style={{ gridColumn: "1 / -1" }}>Non disponibili nei dati importati: {(c.not_available || []).join(", ")}.</p></div>}
    </div>
  );
}
