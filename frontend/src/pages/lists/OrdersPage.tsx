import { useEffect, useState } from "react";
import { api, eyeApi } from "../../lib/api";
import { PageHeader } from "../../components/UI";
import { SupplierOrders } from "./SupplierOrders";

/** Ordini: si sceglie il fornitore e si carica il foglio ordini (.xlsx) come lo si ha. */
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
  const shown = suppliers.filter((n) => !filter.trim() || n.toLowerCase().includes(filter.trim().toLowerCase()));
  return (
    <>
      <PageHeader title="Ordini" subtitle="Scegli il fornitore e carica il suo foglio ordini: consegne giornaliere, prezzi, fatture, verifiche." />
      <section className="panel">
        <label>Fornitore
          <input aria-label="Cerca fornitore" placeholder="Cerca fornitore…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <select aria-label="Fornitore" value={supplier} onChange={(e) => setSupplier(e.target.value)} size={Math.min(8, Math.max(2, shown.length))}>
            {shown.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {supplier ? <SupplierOrders key={supplier} supplier={supplier} /> : <p>Seleziona un fornitore dall'elenco.</p>}
      </section>
    </>
  );
}
