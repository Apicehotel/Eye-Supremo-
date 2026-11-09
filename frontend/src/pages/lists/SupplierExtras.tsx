import { useEffect, useState } from "react";
import { eyeApi, euro } from "../../lib/api";
import { csvOf } from "../../lib/csv";

/** Costi extra del fornitore: righe che non sono prodotti (carburante, accise, trasporto, sconti, resi…). */
export function SupplierExtras({ supplier }: { supplier: string }) {
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError(undefined);
    eyeApi<any>(`/central/supplier-extras?supplier=${encodeURIComponent(supplier)}`, { signal: controller.signal })
      .then(setData).catch((e) => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, [supplier]);
  if (error) return <p>Costi extra non disponibili: {error}</p>;
  if (!data) return <p>Calcolo costi extra…</p>;
  if (!data.categories.length) return <p>Nessuna voce extra rilevata nelle fatture in cache di questo fornitore.</p>;
  const download = () => {
    const rows = [["Categoria", "Righe", "Fatture", "Importo €", "Voce principale"], ...data.categories.map((c: any) => [c.label, c.rows, c.invoices, c.total, c.top[0]?.description ?? ""])];
    const url = URL.createObjectURL(new Blob(["﻿" + csvOf(rows)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = "costi-extra-fornitore.csv"; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="supplier-extras">
      <div className="kpi-grid">
        <div><span>Prodotti (righe normali)</span><b>{euro(data.product_total)}</b></div>
        <div><span>Voci extra</span><b>{euro(data.extra_total)}</b></div>
        <div><span>Righe extra</span><b>{data.extra_rows}</b></div>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Categoria</th><th>Righe</th><th>Fatture</th><th>Importo</th><th>Voci principali</th></tr></thead>
        <tbody>{data.categories.map((c: any) => <tr key={c.key}>
          <td><b>{c.label}</b></td><td>{c.rows}</td><td>{c.invoices}</td><td>{euro(c.total)}</td>
          <td><details><summary>{c.top[0]?.description || "—"}</summary><ul>{c.top.map((t: any, i: number) => <li key={i}>{t.description} · {t.rows} {t.rows === 1 ? "riga" : "righe"} · {euro(t.total)}</li>)}</ul></details></td>
        </tr>)}</tbody></table></div>
      <button className="secondary-btn" onClick={download}>Scarica CSV</button>
      <p><small>{data.note}</small></p>
    </div>
  );
}
