import { useEffect, useMemo, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { eyeApi, euro, shortDate } from "../lib/api";
import { filterRows, isHighlighted } from "../lib/invoiceRows";

export type InvoiceRefTarget = { id: string; highlight?: string };

/** Pulsante standard "Apri fattura" da mettere in ogni riga prodotto. */
export function OpenInvoiceButton({ id, highlight, onOpen }: { id?: string | number | null; highlight?: string; onOpen: (t: InvoiceRefTarget) => void }) {
  if (id === undefined || id === null || id === "") return <span className="muted" title="Riferimento fattura non disponibile">—</span>;
  return (
    <button
      type="button"
      className="secondary-btn open-invoice-btn"
      title="Apri la fattura di riferimento"
      onClick={(event) => { event.stopPropagation(); onOpen({ id: String(id), highlight }); }}
    >
      <FileText size={14} /> Apri
    </button>
  );
}

/** Anteprima della fattura di riferimento (locale, cache o archivio centrale) con la riga cercata evidenziata. */
export function InvoiceViewer({ target, onClose }: { target?: InvoiceRefTarget; onClose: () => void }) {
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string>();
  const [filter, setFilter] = useState("");
  const firstHit = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    setFilter("");
    setData(undefined);
    setError(undefined);
    if (!target) return;
    let alive = true;
    eyeApi<any>(`/invoice-ref/${encodeURIComponent(target.id)}`)
      .then((value) => { if (alive) setData(value); })
      .catch(() => { if (alive) setError("Fattura non trovata né in locale né in archivio centrale."); });
    return () => { alive = false; };
  }, [target?.id]);
  useEffect(() => {
    if (!target) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, onClose]);
  const needle = (target?.highlight || "").trim().toLowerCase();
  const isHit = (row: any) => isHighlighted(row, target?.highlight);
  const query = filter.trim().toLowerCase();
  const rows: any[] = useMemo(() => filterRows(data?.rows || [], filter), [data, filter]);
  const hits = useMemo(() => (data?.rows || []).filter(isHit).length, [data, needle]);
  useEffect(() => { firstHit.current?.scrollIntoView({ block: "center" }); }, [data, needle]);
  if (!target) return null;
  let hitMarked = false;
  const sourceLabel = data?.source === "local" ? "archivio locale" : data?.source === "cache" ? "cache del PC" : data?.source === "central" ? "archivio centrale" : "";
  return (
    <>
      <div className="invoice-ref-backdrop" onClick={onClose} />
      <article className="panel detail-panel detail-preview-panel invoice-ref-panel" role="dialog" aria-label="Fattura di riferimento">
        <div className="panel-title">
          <h2>Fattura {data?.invoice_number || ""}</h2>
          <button className="secondary-btn preview-close" aria-label="Chiudi fattura" title="Chiudi" onClick={onClose}>×</button>
        </div>
        {error ? <p>{error}</p> : !data ? <p className="muted">Carico la fattura…</p> : (
          <>
            <p>
              <b>Fornitore:</b> {data.supplier_name || "—"} · <b>Data:</b> {data.invoice_date ? shortDate(data.invoice_date) : "—"} · <b>Totale:</b> {euro(Number(data.total || 0))}
              {data.taxable != null ? <> · <b>Imponibile:</b> {euro(Number(data.taxable))}</> : null}
              {sourceLabel ? <span className="muted"> · fonte: {sourceLabel}</span> : null}
            </p>
            {data.rows?.length ? (
              <>
              <div className="invoice-ref-search">
                <input type="search" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Cerca nelle righe della fattura…" aria-label="Cerca nelle righe della fattura" />
                <span className="muted">{query ? `${rows.length} di ${data.rows.length} righe` : `${data.rows.length} righe`}{hits ? ` · ${hits} evidenziat${hits === 1 ? "a" : "e"}` : ""}</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Descrizione</th><th>Quantità</th><th>Prezzo unit.</th><th>Totale riga</th></tr></thead>
                  <tbody>
                    {rows.map((row: any, i: number) => {
                      const hit = isHit(row);
                      const ref = hit && !hitMarked ? ((hitMarked = true), firstHit) : undefined;
                      return (
                      <tr key={i} ref={ref} className={hit ? "invoice-ref-hit" : undefined}>
                        <td>{isHit(row) ? <b>{row.original_description || row.normalized_description}</b> : (row.original_description || row.normalized_description || "—")}</td>
                        <td>{row.quantity ?? "—"} {row.original_unit || row.normalized_unit || ""}</td>
                        <td>{row.unit_price != null ? euro(Number(row.unit_price)) : "—"}</td>
                        <td>{row.line_total != null ? euro(Number(row.line_total)) : "—"}</td>
                      </tr>
                    ); })}
                  </tbody>
                </table>
              </div>
              </>
            ) : <p className="muted">Righe della fattura non disponibili offline: riprova con la connessione attiva.</p>}
          </>
        )}
      </article>
    </>
  );
}
