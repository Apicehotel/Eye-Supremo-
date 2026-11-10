import { useEffect, useState } from "react";
import { api, eyeApi } from "../../lib/api";
import { PageHeader } from "../../components/UI";
import { SupplierOrders } from "./SupplierOrders";

/** Ordini: si cerca il fornitore e i dati si ricavano dalle fatture (nessun caricamento obbligatorio). */
export function OrdersPage() {
  const [suppliers, setSuppliers] = useState<string[]>([]);
  const [supplier, setSupplier] = useState("");
  const [filter, setFilter] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      let names: string[] = [];
      try {
        const data = await eyeApi<any>(`/central/suppliers?limit=2000`, { signal: controller.signal });
        names = (data.items || []).map((s: any) => String(s.ragione_sociale || "")).filter(Boolean);
      } catch {
        try { names = (await api<any[]>(`/suppliers`, { signal: controller.signal })).map((s) => String(s.ragione_sociale || "")).filter(Boolean); } catch { /* elenco vuoto */ }
      }
      if (!controller.signal.aborted) setSuppliers([...new Set(names)].sort((a, b) => a.localeCompare(b, "it")));
    })();
    return () => controller.abort();
  }, []);
  const query = filter.trim().toLowerCase();
  const shown = query ? suppliers.filter((n) => n.toLowerCase().includes(query)).slice(0, 8) : [];
  const pick = (name: string) => { setSupplier(name); setFilter(""); };
  return (
    <>
      <PageHeader title="Ordini" subtitle="Scegli il fornitore: consegne giornaliere, prezzi, fatture e verifiche si ricavano da sole dalle fatture, senza caricare nulla." />
      <section className="panel">
        <div className="orders-picker">
          <label>Fornitore
            <input aria-label="Cerca fornitore" placeholder={supplier || "Scrivi per cercare il fornitore…"} value={filter} autoComplete="off"
              onChange={(e) => setFilter(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && shown[0]) pick(shown[0]); if (e.key === "Escape") setFilter(""); }} />
          </label>
          {supplier && !filter && <span className="orders-picked"><b>{supplier}</b> <button type="button" className="secondary-btn" onClick={() => setSupplier("")}>Cambia</button></span>}
          {shown.length > 0 && <ul className="orders-suggest" role="listbox">{shown.map((n) => <li key={n}><button type="button" role="option" aria-selected={n === supplier} onClick={() => pick(n)}>{n}</button></li>)}</ul>}
          {query && !shown.length && <p className="muted">Nessun fornitore corrisponde a «{filter}».</p>}
        </div>
        {supplier ? <SupplierOrders key={supplier} supplier={supplier} /> : <p>Scrivi il nome del fornitore e sceglilo dall'elenco.</p>}
      </section>
    </>
  );
}
